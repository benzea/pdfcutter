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
import pango
import pangocairo
import gobject
import gtk
import poppler
import thread
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

HEADER_FONT = 'Bitstream Vera Serif 10'

class Box(gobject.GObject):
	__gtype_name__ = 'PDFCutterBox'
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([]))
	}
	def __init__(self):
		gobject.GObject.__init__(self)
		self._spage = 0
		self._sx = 0
		self._sy = 0
		self._width = 0
		self._height = 0
		self._model = None

		self._dscale = 2.0
		self._dpage = 0
		self._dx = 0
		self._dy = 0
		
		# This can be true or false, ie. switches the "color" used
		# for layout purposes
		self.colored = False

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

	sx = gobject.property(type=float, getter=get_sx, setter=set_sx)
	sy = gobject.property(type=float, getter=get_sy, setter=set_sy)
	spage = gobject.property(type=int, getter=get_spage, setter=set_spage)
	width = gobject.property(type=float, getter=get_width, setter=set_width)
	height = gobject.property(type=float, getter=get_height, setter=set_height)

	dx = gobject.property(type=float, getter=get_dx, setter=set_dx)
	dy = gobject.property(type=float, getter=get_dy, setter=set_dy)
	dpage = gobject.property(type=int, getter=get_dpage, setter=set_dpage)
	dscale = gobject.property(type=float, getter=get_dscale, setter=set_dscale)

	def __eq__(self, other):
		return self is other

	def __cmp__(self, other):
		if self.dpage < other.dpage:
			return -1
		if self.dpage > other.dpage:
			return 1
		return 0

class Model(gobject.GObject):
	__gtype_name__ = 'PDFCutterModel'
	__gsignals__ = {
		'box-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'box-zpos-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'box-added': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'box-removed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'page-rendered': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'box-rendered': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'header-text-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ())
	}

	def __init__(self, pdffile=None, loadfile=None):
		gobject.GObject.__init__(self)

		self.pdffile = pdffile
		self.loadfile = loadfile
		self.header_text = "HEADER TEXT"
		self._boxes = []
		self._rendered_boxes = LRU(200)
		self._rendered_pages = LRU(5)
		self._box_render_queue = []
		self._page_render_queue = []
		self._render_queue_lock = thread.allocate_lock()
		# poppler does not seem to be entirely thread safe wrt. to rendering at least
		self._document_lock = thread.allocate_lock()
		self._render_thread_running = False

		if loadfile:
			self._load_from_file()

		self.document = \
			poppler.document_new_from_file('file://' + self.pdffile, None)

	def set_header_text(self, value):
		self.header_text = value
		self.emit('header-text-changed')

	def get_rendered_box_or_queue (self, box, scale, x_offset, y_offset):
		try:
			# Try to retrieve a preprendered box
			self._render_queue_lock.acquire()
			result, _scale, page, x, y, width, height, _x_offset, _y_offset = self._rendered_boxes[box]
			self._render_queue_lock.release()

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
			# Nothing, there, queue the rendering
			self._render_queue_lock.release()
			self._queue_box_render_at_scale(box, scale, x_offset, y_offset)

	def get_rendered_page_or_queue (self, page, scale, x_offset, y_offset):
		try:
			# Try to retrieve a preprendered box
			self._render_queue_lock.acquire()
			result, _scale, _x_offset, _y_offset = self._rendered_pages[page]
			self._render_queue_lock.release()

			if scale != _scale or x_offset != _x_offset or y_offset != _y_offset:
				# Queue a render at the correct scale
				self._queue_page_render_at_scale(page, scale, x_offset, y_offset)
			return result, _scale, _x_offset, _y_offset
		except KeyError:
			# Nothing, there, queue the rendering
			self._render_queue_lock.release()
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
			os.spawnv(os.P_WAIT, '/usr/bin/convert', ['convert', png, '-monochrome', tif])
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
		cr = pangocairo.CairoContext(cr)
		font = pango.FontDescription(HEADER_FONT)
		font.set_weight(pango.WEIGHT_BOLD)
		page = 0

		layout = cr.create_layout()
		layout.set_text(self.header_text)
		layout.set_font_description(font)
		cr.move_to(PADDING, PADDING)
		cr.show_layout(layout)

		progress = 0
		gobject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *pbargs)
		for box in self.iter_boxes():
			while box.dpage > page:
				page += 1
				write_tif(surface, tmpdir, page)
				cr.set_source_rgb(1, 1, 1)
				cr.paint()
				layout = cr.create_layout()
				layout.set_text(self.header_text)
				layout.set_font_description(font)
				cr.move_to(PADDING, PADDING - 2)
				cr.show_layout(layout)
			cr.save()
			cr.translate(+box.dx, +box.dy)
			cr.scale(box.dscale, box.dscale)
			cr.rectangle(0, 0, box.width*box.dscale, box.height*box.dscale)
			cr.clip()
			cr.translate(-box.sx, -box.sy)
			self._document_lock.acquire()
			self.document.get_page(box.spage).render_for_printing(cr)
			self._document_lock.release()
			cr.restore()

			progress += 1
			gobject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes)+1, *pbargs)

		page += 1
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
		gobject.idle_add(self._emit_progress_cb, progress_cb, len(self._boxes)+1, len(self._boxes)+1, *pbargs)


	def _real_emit_pdf(self, filename, progress_cb, *args):
		self.sort_boxes()
		width, height = self.document.get_page(0).get_size()
		surface = cairo.PDFSurface(filename, width, height)
		cr = cairo.Context(surface)
		cr = pangocairo.CairoContext(cr)
		font = pango.FontDescription(HEADER_FONT)
		font.set_weight(pango.WEIGHT_BOLD)
		page = 0

		layout = cr.create_layout()
		layout.set_text(self.header_text)
		layout.set_font_description(font)
		cr.move_to(PADDING, PADDING)
		cr.show_layout(layout)

		progress = 0
		gobject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *args)
		for box in self.iter_boxes():
			while box.dpage > page:
				page += 1
				cr.show_page()
				layout = cr.create_layout()
				layout.set_text(self.header_text)
				layout.set_font_description(font)
				cr.move_to(PADDING, PADDING - 2)
				cr.show_layout(layout)
			cr.save()
			cr.translate(+box.dx, +box.dy)
			cr.scale(box.dscale, box.dscale)
			cr.rectangle(0, 0, box.width, box.height)
			cr.clip()
			cr.translate(-box.sx, -box.sy)
			self._document_lock.acquire()
			self.document.get_page(box.spage).render_for_printing(cr)
			self._document_lock.release()
			cr.restore()

			progress += 1
			gobject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *args)
		# done ...
		gobject.idle_add(self._emit_progress_cb, progress_cb, progress, len(self._boxes), *args)

	def emit_pdf(self, filename, progress_cb, *args):
		thread.start_new_thread(self._real_emit_pdf, (filename, progress_cb) + args)

	def emit_tif(self, filename, progress_cb, *args):
		thread.start_new_thread(self._real_emit_tif, (filename, progress_cb) + args)

	def iter_boxes(self):
		for box in self._boxes:
			yield box

	def sort_boxes(self):
		self._boxes.sort()

	def add_box(self, box):
		ypos = PADDING
		page = 0
		self._boxes.sort()
		for b in self._boxes:
			if b.dpage > page:
				page = b.dpage
				ypos = PADDING

			if b.dx > box.dx + box.width or \
			   b.dx + b.width < box.dx:
				continue
			ypos = max(ypos, b.dy + b.height)
		width, height = self.document.get_page(0).get_size()
		if ypos + box.height > height - PADDING:
			page += 1
			ypos = PADDING
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
		self._render_queue_lock.acquire()
		for queue in self._box_render_queue:
			if queue[0] != box:
				continue

			if queue[1] != scale or queue[2] != x_offset or queue[3] != y_offset:
				self._box_render_queue.remove(queue)
			else:
				self._render_queue_lock.release()
				return
					
		self._box_render_queue.append((box, scale, x_offset, y_offset))
		# Recreate thread if neccessary
		if not self._render_thread_running:
			thread.start_new_thread(self._render_thread, ())
			self._render_thread_running = True
		self._render_queue_lock.release()

	def _queue_page_render_at_scale(self, page, scale, x_offset, y_offset):
		self._render_queue_lock.acquire()

		for queue in self._page_render_queue:
			if queue[0] == page:
				if queue[1] != scale or queue[2] != x_offset or queue[3] != y_offset:
					self._page_render_queue.remove(queue)
				else:
					self._render_queue_lock.release()
					return

		self._page_render_queue.append((page, scale, x_offset, y_offset))
		# Recreate thread if neccessary
		if not self._render_thread_running:
			thread.start_new_thread(self._render_thread, ())
			self._render_thread_running = True
		self._render_queue_lock.release()

	def _render_thread(self):
		# Just do a render run on pages/boxes
		while True:
			self._render_page()
			self._render_box()

			self._render_queue_lock.acquire()
			if len(self._box_render_queue) == 0 and \
			   len(self._page_render_queue) == 0:
				self._render_thread_running = False
				self._render_queue_lock.release()
				return

			self._render_queue_lock.release()

	def _emit_box_rendered(self, box):
		self.emit("box-rendered", box)
		return False

	def _render_box(self):
		self._render_queue_lock.acquire()
		if len(self._box_render_queue) == 0:
			self._render_queue_lock.release()
			return
		data = self._box_render_queue.pop()
		self._render_queue_lock.release()

		box = data[0]
		page_number, x, y, width, height = box.spage, box.sx, box.sy, box.width, box.height
		scale = data[1]
		x_offset = data[2]
		y_offset = data[3]

		page = self.document.get_page(page_number)
		scaled_width = width + 1
		scaled_height = height + 1
		scaled_width = scaled_width * scale
		scaled_height = scaled_height * scale
		try:
			surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(math.ceil(scaled_width)), int(math.ceil(scaled_height)))
		except MemoryError:
			sys.stderr.write("Cannot render box at this zoom, not enough memory!\n")
			return
			pass
		cr = cairo.Context(surface)
		cr.set_source_rgba(0, 0, 0, 0)
		cr.set_operator(cairo.OPERATOR_SOURCE)
		cr.paint()

		cr.set_operator(cairo.OPERATOR_OVER)
		cr.scale(scale, scale)
		cr.translate(-x + x_offset, -y + y_offset)
		self._document_lock.acquire()
		page.render(cr)
		self._document_lock.release()

		self._render_queue_lock.acquire()
		self._rendered_boxes[box] = (surface, scale, page_number, x, y, width, height, x_offset, y_offset)
		self._render_queue_lock.release()

		gobject.idle_add(self._emit_box_rendered, box)

	def _emit_page_rendered(self, page):
		self.emit("page-rendered", page)
		return False

	def _render_page(self):
		self._render_queue_lock.acquire()
		if len(self._page_render_queue) == 0:
			self._render_queue_lock.release()
			return
		data = self._page_render_queue.pop()
		self._render_queue_lock.release()

		page_number = data[0]
		scale = data[1]
		x_offset = data[2]
		y_offset = data[3]

		page = self.document.get_page(page_number)
		width, height = page.get_size()
		width *= scale
		height *= scale
		try:
			surface = cairo.ImageSurface(cairo.FORMAT_RGB24, int(width + 1), int(height + 1))
		except MemoryError:
			sys.stderr.write("Cannot render page at this zoom, not enough memory!\n")
			return
			pass
		cr = cairo.Context(surface)
		cr.set_source_rgba(1, 1, 1)
		cr.paint()

		cr.scale(scale, scale)
		cr.translate(x_offset, y_offset)
		self._document_lock.acquire()
		page.render(cr)
		self._document_lock.release()

		self._render_queue_lock.acquire()
		self._rendered_pages[page_number] = (surface, scale, x_offset, y_offset)
		self._render_queue_lock.release()

		gobject.idle_add(self._emit_page_rendered, page_number)

