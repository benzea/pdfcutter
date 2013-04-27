# -*- coding: utf-8 -*-
# PDFCutter
#
# Copyright (C) 2009, Benjamin Berg <benjamin@sipsolutions.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or   
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the  
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import cairo
import sys
from gi.repository import GLib
from gi.repository import Pango
from gi.repository import PangoCairo
from gi.repository import GObject
from gi.repository import Poppler
import multiprocessing
from gprocess import GProcess
import os
import math
import tempfile
from lru import LRU

def relpath(path, start=os.path.curdir):
	"""Return a relative version of a path"""

	if not path:
		raise ValueError("no path specified")
	start_list = os.path.abspath(start).split(os.path.sep)
	path_list = os.path.abspath(path).split(os.path.sep)
	if start_list[0].lower() != path_list[0].lower():
		unc_path, rest = os.path.splitunc(path)
		unc_start, rest = os.path.splitunc(start)
		if bool(unc_path) ^ bool(unc_start):
			raise ValueError("Cannot mix UNC and non-UNC paths (%s and %s)"
			                 % (path, start))
		else:
			raise ValueError("path is on drive %s, start on drive %s"
			                 % (path_list[0], start_list[0]))
	# Work out how much of the filepath is shared by start and path.
	for i in range(min(len(start_list), len(path_list))):
		if start_list[i].lower() != path_list[i].lower():
			break
		else:
			i += 1

	rel_list = [os.path.pardir] * (len(start_list)-i) + path_list[i:]
	if not rel_list:
		return os.path.curdir
	return os.path.join(*rel_list)

PADDING = 10*72/25.4
TOP_PADDING = 17*72/25.4

HEADER_FONT = 'Bitstream Vera Serif 10'

class Box(GObject.GObject):
	__gtype_name__ = 'PDFCutterBox'
	__gsignals__ = {
		'changed': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ([]))
	}
	def __init__(self):
		GObject.GObject.__init__(self)
		self._spage = 0
		self._sx = 0
		self._sy = 0
		self._width = 0
		self._height = 0
		self._model = None

		self._dscale = 1.0
		self._dpage = 0
		self._dx = 0
		self._dy = 0
		
	def get_sx(self):
		return self._sx
	def set_sx(self, value):
		# Keep the source and dest value in sync to some extend
		self._dx += value - self._sx
		self._sx = value
		self._emit_change()

	def get_sy(self):
		return self._sy
	def set_sy(self, value):
		self._sy = value
		self._emit_change()

	def get_spage(self):
		return self._spage
	def set_spage(self, value):
		self._spage = value
		self._emit_change()

	def get_width(self):
		return self._width
	def set_width(self, value):
		self._width = value
		self._emit_change()

	def get_height(self):
		return self._height
	def set_height(self, value):
		self._height = value
		self._emit_change()

	def get_dx(self):
		return self._dx
	def set_dx(self, value):
		self._dx = value
		self._emit_change()

	def get_dy(self):
		return self._dy
	def set_dy(self, value):
		self._dy = value
		self._emit_change()

	def get_dpage(self):
		return self._dpage
	def set_dpage(self, value):
		self._dpage = value
		self._emit_change()
		
		if self._model:
			# Keep boxes sorted
			self._model.sort_boxes()
			# Emit the models signal ...
			self._model.emit("box-zpos-changed", self)

	def get_dscale(self):
		return self._dscale
	def set_dscale(self, value):
		self._dscale = value
		self._emit_change()

	def _emit_change(self):
		self.emit("changed")
		# so we do not need to connect to all the boxes in the model
		if self._model:
			self._model.emit("box-changed", self)

	sx = GObject.property(type=float, getter=get_sx, setter=set_sx)
	sy = GObject.property(type=float, getter=get_sy, setter=set_sy)
	spage = GObject.property(type=int, getter=get_spage, setter=set_spage)
	width = GObject.property(type=float, getter=get_width, setter=set_width)
	height = GObject.property(type=float, getter=get_height, setter=set_height)

	dx = GObject.property(type=float, getter=get_dx, setter=set_dx)
	dy = GObject.property(type=float, getter=get_dy, setter=set_dy)
	dpage = GObject.property(type=int, getter=get_dpage, setter=set_dpage)
	dscale = GObject.property(type=float, getter=get_dscale, setter=set_dscale)

class Model(GObject.GObject):
	__gtype_name__ = 'PDFCutterModel'
	__gsignals__ = {
		'box-changed': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ([object])),
		'box-zpos-changed': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ([object])),
		'box-added': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ([object])),
		'box-removed': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ([object])),
		'page-rendered': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ([object])),
		'box-rendered': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ([object])),
		'header-text-changed': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ())
	}

	def __init__(self, pdffile=None, loadfile=None):
		GObject.GObject.__init__(self)

		self.pdffile = pdffile
		self.loadfile = loadfile
		self.header_text = "HEADER TEXT"
		self._boxes = []
		self._rendered_boxes = LRU(200)
		self._rendered_pages = LRU(5)

		self._box_render_process = GProcess(target=self._box_render_proc, childcb=self._box_rendered_wakeup)
		self._page_render_process = GProcess(target=self._page_render_proc, childcb=self._page_rendered_wakeup)

		# These are only for the main process, to prevent an item from being
		# queued twice.
		self._box_render_queue = []
		self._page_render_queue = []

		self._box_render_pipe_p, self._box_render_pipe_c = multiprocessing.Pipe()
		self._page_render_pipe_p, self._page_render_pipe_c = multiprocessing.Pipe()

		if loadfile:
			self._load_from_file()

		self.document = \
			Poppler.Document.new_from_file('file://' + self.pdffile, None)

		self._box_render_process.start()
		self._page_render_process.start()

	def set_header_text(self, value):
		self.header_text = value
		self.emit('header-text-changed')

	def get_rendered_box_or_queue (self, box, scale, x_offset, y_offset, similar_surface):
		try:
			# Try to retrieve a preprendered box
			result, _scale, page, x, y, width, height, dscale, _x_offset, _y_offset, uploaded = self._rendered_boxes[box]

			# Check whether surface can and is not uploaded to the X server
			if similar_surface and not uploaded:
				iwidth, iheight = result.get_width(), result.get_height()
				surf = similar_surface.create_similar(cairo.CONTENT_COLOR_ALPHA, iwidth, iheight)
				cr = cairo.Context(surf)
				cr.set_operator(cairo.OPERATOR_SOURCE)
				cr.set_source_surface(result, 0, 0)
				cr.paint()

				result = surf
				self._rendered_boxes[box] = (result, _scale, page, x, y, width, height, dscale, _x_offset, _y_offset, True)

			if scale != _scale or page != box.spage or x != box.sx or \
			   y != box.sy or width != box.width or height != box.height or\
			   x_offset != _x_offset or y_offset != _y_offset:
				# Queue a render at the correct scale
				self._queue_box_render_at_scale(box, scale, x_offset, y_offset)

			if page != box.spage or x != box.sx or \
			   y != box.sy or width != box.width or height != box.height:
				result = None

			if result is not None:
				return result, _scale, _x_offset, _y_offset
		except KeyError:
			self._queue_box_render_at_scale(box, scale, x_offset, y_offset)

	def get_rendered_page_or_queue (self, page, scale, x_offset, y_offset, similar_surface):
		try:
			result, _page, _scale, _x_offset, _y_offset, uploaded = self._rendered_pages[page]

			# Check whether surface can and is not uploaded to the X server
			if similar_surface and not uploaded:
				iwidth, iheight = result.get_width(), result.get_height()
				surf = similar_surface.create_similar(cairo.CONTENT_COLOR, iwidth, iheight)
				cr = cairo.Context(surf)
				cr.set_operator(cairo.OPERATOR_SOURCE)
				cr.set_source_surface(result, 0, 0)
				cr.paint()

				result = surf
				self._rendered_pages[page] = (result, _page, _scale, _x_offset, _y_offset, True)

			if scale != _scale or x_offset != _x_offset or y_offset != _y_offset:
				# Queue a render at the correct scale
				self._queue_page_render_at_scale(page, scale, x_offset, y_offset)

			return result, _scale, _x_offset, _y_offset
		except KeyError:
			self._queue_page_render_at_scale(page, scale, x_offset, y_offset)
			return None

	def _emit_progress_cb(self, progress_cb, pos, count, *args):
		progress_cb(pos, count, *args)

	def _real_emit_tif(self, filename, progress_cb, *pbargs):
		tmpdir = tempfile.mkdtemp()
		
		def write_tif(surface, tmpdir, page):
			png = os.path.join(tmpdir, "%i.png" % page)
			tif = os.path.join(tmpdir, "%i.tif" % page)
			surface.write_to_png(png)
			# We need to use Group4, or some programs cannot handle the file!
			# We also need to force a resolution of 300 dpi on the tiff (the pngs are wrong)
			os.spawnv(os.P_WAIT, '/usr/bin/convert', ['convert', png, '-units', 'PixelsPerInch', '-density', '300', '-monochrome', '-compress', 'Group4', tif])
			os.unlink(png)

		self.sort_boxes()
		width, height = self.document.get_page(0).get_size()
		width_px = int(width / 72.0 * 300)
		height_px = int(height / 72.0 * 300)

		surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width_px, height_px)
		cr = cairo.Context(surface)
		cr.set_source_rgb(1, 1, 1)
		cr.paint()
		cr.scale(300.0 / 72.0, 300 / 72.0)
		font = Pango.FontDescription(HEADER_FONT)
		font.set_weight(Pango.Weight.BOLD)
		page = 0

		def show_text():
			layout = PangoCairo.create_layout(cr)
			layout.set_text(self.header_text, len(self.header_text))
			layout.set_font_description(font)
			cr.move_to(PADDING, PADDING)
			cr.set_source_rgb(0, 0, 0)
			PangoCairo.show_layout(cr, layout)

		progress = 0
		GObject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *pbargs)
		for box in self.iter_boxes():
			while box.dpage > page:
				page += 1
				show_text()
				write_tif(surface, tmpdir, page)
				cr.set_source_rgb(1, 1, 1)
				cr.paint()
				yield
			cr.save()
			cr.translate(+box.dx, +box.dy)
			cr.scale(box.dscale, box.dscale)
			cr.rectangle(0, 0, box.width, box.height)
			cr.clip()
			cr.translate(-box.sx, -box.sy)
			self.document.get_page(box.spage).render_for_printing(cr)
			cr.restore()

			progress += 1
			GObject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes)+1, *pbargs)
			# XXX: Hack to split up the task into chunks using the mainloop
			yield

		page += 1
		show_text()
		write_tif(surface, tmpdir, page)
		
		input = [ os.path.join(tmpdir, "%i.tif" % i) for i in xrange(1, page+1) ]

		args = [ 'tiffcp' ]
		args += input
		args.append(filename)
		os.spawnv(os.P_WAIT, '/usr/bin/tiffcp', args)

		for file in input:
			os.unlink(file)
		os.rmdir(tmpdir)

		# done ...
		GObject.idle_add(self._emit_progress_cb, progress_cb, len(self._boxes)+1, len(self._boxes)+1, *pbargs)


	def _real_emit_pdf(self, filename, progress_cb, *args):
		self.sort_boxes()
		width, height = self.document.get_page(0).get_size()
		surface = cairo.PDFSurface(filename, width, height)
		# Fallback resolution
		surface.set_fallback_resolution(300, 300)
		cr = cairo.Context(surface)
		font = Pango.FontDescription(HEADER_FONT)
		font.set_weight(Pango.Weight.BOLD)
		page = 0

		def show_text():
			layout = PangoCairo.create_layout(cr)
			layout.set_text(self.header_text, len(self.header_text))
			layout.set_font_description(font)
			cr.move_to(PADDING, PADDING)
			cr.set_source_rgb(0, 0, 0)
			PangoCairo.show_layout(cr, layout)

		progress = 0
		GObject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *args)
		for box in self.iter_boxes():
			while box.dpage > page:
				page += 1
				show_text()
				cr.show_page()
				surface.set_size(width, height)
			cr.save()
			cr.translate(+box.dx, +box.dy)
			cr.scale(box.dscale, box.dscale)
			cr.rectangle(0, 0, box.width, box.height)
			cr.clip()
			cr.translate(-box.sx, -box.sy)
			self.document.get_page(box.spage).render_for_printing(cr)
			cr.restore()

			progress += 1

			GObject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *args)
			# XXX: Hack to split up the task into chunks using the mainloop
			yield

		show_text()
		# done ...
		GObject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *args)

	def emit_pdf(self, filename, progress_cb, *args):
		# XXX: Blocks for now!
		list(self._real_emit_pdf(filename, progress_cb, *args))

	def main_iter_emit_pdf(self, filename, progress_cb, *args):
		iterator = self._real_emit_pdf(filename, progress_cb, *args)

		def do_next():
			try:
				iterator.next()
			except StopIteration:
				return False

			return True

		GLib.idle_add(do_next)

	def emit_tif(self, filename, progress_cb, *args):
		# XXX: Blocks for now!
		list(self._real_emit_tif(filename, progress_cb, *args))

	def main_iter_emit_tif(self, filename, progress_cb, *args):
		iterator = self._real_emit_tif(filename, progress_cb, *args)

		def do_next():
			try:
				iterator.next()
			except StopIteration:
				return False

			return True

		GLib.idle_add(do_next)

	def iter_boxes(self):
		for box in self._boxes:
			yield box

	def sort_boxes(self):
		prev_sorting = list(self._boxes)
		self._boxes.sort(key=lambda box: box.dpage)
		# Simple (and really stupid) algorithm ... ie. emit
		# z-pos change for every item where the index has changed.
		for i in range(len(prev_sorting)):
			if prev_sorting[i] != self._boxes[i]:
				self.emit("box-zpos-changed", prev_sorting[i])

	def add_box(self, box):
		ypos = TOP_PADDING
		page = 0
		self.sort_boxes()
		for b in self._boxes:
			if b.dpage > page:
				page = b.dpage
				ypos = PADDING

			if b.dx > box.dx + box.width * box.dscale or \
			   b.dx + b.width * b.dscale < box.dx:
				continue
			ypos = max(ypos, b.dy + b.height * b.dscale)
		width, height = self.document.get_page(0).get_size()
		if ypos + box.height * box.dscale > height - PADDING:
			page += 1
			ypos = TOP_PADDING
		box.dy = ypos
		box.dpage = page

		self._boxes.append(box)
		box._model = self
		self.emit("box-added", box)

	def remove_box(self, box):
		self._boxes.remove(box)
		self.emit("box-removed", box)

	def get_lower_box(self, box):
		index = self._boxes.index(box)
		if index > 0 and self._boxes[index-1].dpage == box.dpage:
			return self._boxes[index-1]
		else:
			return None

	def move_boxes_down(self, boxes):
		tmp = []
		for box in boxes:
			tmp.append((self._boxes.index(box), box))
		tmp.sort()

		for index, box in tmp:
			self.move_box_down(box)

	def move_boxes_up(self, boxes):
		tmp = []
		for box in boxes:
			tmp.append((self._boxes.index(box), box))
		tmp.sort(reverse=True)

		for index, box in tmp:
			self.move_box_up(box)

	def move_box_down(self, box):
		index = self._boxes.index(box)
		if index > 0 and self._boxes[index-1].dpage == box.dpage:
			_ = self._boxes[index-1]
			self._boxes[index-1] = self._boxes[index]
			self._boxes[index] = _
			self.emit("box-zpos-changed", box)

	def move_box_up(self, box):
		index = self._boxes.index(box)
		if index+1 < len(self._boxes) and self._boxes[index+1].dpage == box.dpage:
			_ = self._boxes[index+1]
			self._boxes[index+1] = self._boxes[index]
			self._boxes[index] = _
			self.emit("box-zpos-changed", box)

	def save_to_file(self, filename):
		self.loadfile = filename
		f = open(filename, 'w')
		f.write('PdfCutter File\n')
		dirname = os.path.dirname(os.path.abspath(filename))
		pdffile = relpath(self.pdffile, dirname)
		f.write(pdffile)
		f.write('\n')
		f.write(self.header_text)
		f.write('\n')
		for b in self._boxes:
			f.write("%f %f %f %f %f %f %f %i %i\n" % (b.sx, b.sy, b.width, b.height, b.dx, b.dy, b.dscale, b.spage, b.dpage))

	def _load_from_file(self):
		f = open(self.loadfile, "r")
		assert(f.readline() == 'PdfCutter File\n')
		self.pdffile = f.readline()[:-1]
		if not os.path.isabs(self.pdffile):
			self.pdffile = os.path.join(os.path.dirname(os.path.abspath(self.loadfile)), self.pdffile)
			self.pdffile = os.path.abspath(self.pdffile)
		self.header_text = f.readline()[:-1]
		for line in f.readlines():
			data = line.split()
			b = Box()
			b.sx = float(data[0])
			b.sy = float(data[1])
			b.width = float(data[2])
			b.height = float(data[3])
			b.dx = float(data[4])
			b.dy = float(data[5])
			if len(data) == 9:
				b.dscale = float(data[6])
				b.spage = int(data[7])
				b.dpage = int(data[8])
			elif len(data) == 8:
				b.dscale = 1.0
				b.spage = int(data[6])
				b.dpage = int(data[7])
			else:
				raise AssertionError
			b._model = self
			self._boxes.append(b)

	def _queue_box_render_at_scale(self, box, scale, x_offset, y_offset):
		render_info = (scale, box.spage, box.sx, box.sy, box.width, box.height, box.dscale, x_offset, y_offset)

		for b, info in self._box_render_queue:
			if b == box and info == render_info:
				return

		# Save in internal list
		self._box_render_queue.append((box, render_info))
		# And send item over the wire
		self._box_render_pipe_p.send(render_info)

	def _queue_page_render_at_scale(self, page, scale, x_offset, y_offset):
		render_info = (page, scale, x_offset, y_offset)

		if render_info in self._page_render_queue:
			return

		self._page_render_queue.append(render_info)
		self._page_render_pipe_p.send(render_info)

	def _box_render_proc(self):
		# This function runs in a separate process!

		while True:
			obj = self._box_render_pipe_c.recv()
			if obj == 'quit':
				return

			# Wake parent first (in case data does not fit into buffer)
			self._box_render_process.wake_parent()
			self._box_render_pipe_c.send(self._pack_surface(self._render_box(obj)))

	def _page_render_proc(self):
		# This function runs in a separate process!

		while True:
			obj = self._page_render_pipe_c.recv()
			if obj == 'quit':
				return

			# Wake parent first (in case data does not fit into buffer)
			self._page_render_process.wake_parent()
			self._page_render_pipe_c.send(self._pack_surface(self._render_page(obj)))

	def _recreate_surface(self, surface):
		f, width, height, stride, data = surface
		surface = cairo.ImageSurface(f, width, height)

		# Has to be the same ... same forked() process ...
		assert stride == surface.get_stride()
		d = surface.get_data()
		d[:] = data

		surface.mark_dirty()

		return surface

	b = False

	def _pack_surface(self, surface):
		surface.flush()

		f = surface.get_format()
		width = surface.get_width()
		height = surface.get_height()
		stride = surface.get_stride()
		data = surface.get_data()
		data = str(data)

		return f, width, height, stride, data

	def _box_rendered_wakeup(self, proc):
		# XXX: Assumes that nothing ever goes wrong ...
		box, data = self._box_render_queue.pop(0)

		surface_data = self._box_render_pipe_p.recv()
		surface = self._recreate_surface(surface_data)

		self._rendered_boxes[box] = (surface,) + data + (False,)
		GLib.idle_add(self._emit_box_rendered, box)

	def _page_rendered_wakeup(self, proc):
		# XXX: Assumes that nothing ever goes wrong ...
		data = self._page_render_queue.pop(0)

		surface_data = self._page_render_pipe_p.recv()
		surface = self._recreate_surface(surface_data)

		self._rendered_pages[data[0]] = (surface,) + data + (False,)
		GLib.idle_add(self._emit_page_rendered, data[0])

	def _emit_box_rendered(self, box):
		self.emit("box-rendered", box)
		return False

	def _emit_page_rendered(self, page):
		self.emit("page-rendered", page)
		return False

	def _render_box(self, data):
		scale, page_number, x, y, width, height, scale, x_offset, y_offset = data

		page = self.document.get_page(page_number)
		scaled_width = width + 1
		scaled_height = height + 1
		scaled_width = scaled_width * scale
		scaled_height = scaled_height * scale
		try:
			surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(math.ceil(scaled_width)), int(math.ceil(scaled_height)))
		except MemoryError:
			sys.stderr.write("Cannot render box at this zoom, not enough memory!\n")
			return None

		cr = cairo.Context(surface)
		cr.set_source_rgba(0, 0, 0, 0)
		cr.set_operator(cairo.OPERATOR_SOURCE)
		cr.paint()

		cr.set_operator(cairo.OPERATOR_OVER)
		cr.scale(scale, scale)
		cr.translate(-x - x_offset, -y - y_offset)
		page.render_for_printing(cr)

		return surface

	def _render_page(self, data):
		page_number, scale, x_offset, y_offset = data

		page = self.document.get_page(page_number)
		width, height = page.get_size()
		width *= scale
		height *= scale
		try:
			surface = cairo.ImageSurface(cairo.FORMAT_RGB24, int(width + 1), int(height + 1))
		except MemoryError:
			sys.stderr.write("Cannot render page at this zoom, not enough memory!\n")
			return None

		cr = cairo.Context(surface)
		cr.set_source_rgba(1, 1, 1)
		cr.paint()

		cr.scale(scale, scale)
		cr.translate(-x_offset, -y_offset)
		page.render_for_printing(cr)

		return surface

	def shutdown(self):
		# Let the subprocesses quit.
		if os.getpid() != self._page_render_process.pid:
			self._box_render_pipe_p.send('quit')
			self._page_render_pipe_p.send('quit')

			self._box_render_process.join(2)
			self._page_render_process.join(2)

			self._box_render_process.terminate()
			self._page_render_process.terminate()

