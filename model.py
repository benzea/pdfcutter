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
import gobject
import gtk
import poppler
import thread
import math
from lru import LRU

_PADDING = 10

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

	def __cmp__(self, other):
		if self.dpage < other.dpage:
			return -1
		if self.dpage > other.dpage:
			return 1
		if self.dy < other.dy:
			return -1
		if self.dy > other.dy:
			return 1
		if self.dx < other.dx:
			return -1
		if self.dx > other.dx:
			return 1
		return 0

class Model(gobject.GObject):
	__gtype_name__ = 'PDFCutterModel'
	__gsignals__ = {
		'box-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'box-added': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'box-removed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'page-rendered': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object])),
		'box-rendered': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([object]))
	}

	def __init__(self, pdffile=None, loadfile=None):
		gobject.GObject.__init__(self)

		self.pdffile = pdffile
		self.loadfile = loadfile
		self._boxes = []
		self._rendered_boxes = LRU(30)
		self._rendered_pages = LRU(5)
		self._box_render_queue = []
		self._page_render_queue = []
		self._render_queue_lock = thread.allocate_lock()
		self._render_thread_running = False

		if loadfile:
			self._load_from_file()

		self.document = \
			poppler.document_new_from_file(self.pdffile, None)

	def get_rendered_box_or_queue (self, box, scale):
		try:
			# Try to retrieve a preprendered box
			self._render_queue_lock.acquire()
			result, rscale, page, x, y, width, height, offset_x, offset_y = self._rendered_boxes[box]
			self._render_queue_lock.release()

			if rscale != scale or page != box.spage or x != box.sx or \
			   y != box.sy or width != box.width or height != box.height:
				# Queue a render at the correct scale
				self._queue_box_render_at_scale(box, scale)

			if page != box.spage or x != box.sx or \
			   y != box.sy or width != box.width or height != box.height:
				result = None
			if result is not None:
				return result, rscale, offset_x, offset_y
		except KeyError:
			# Nothing, there, queue the rendering
			self._render_queue_lock.release()
			self._queue_box_render_at_scale(box, scale)

	def get_rendered_page_or_queue (self, page, scale):
		try:
			# Try to retrieve a preprendered box
			self._render_queue_lock.acquire()
			result, rscale = self._rendered_pages[page]
			self._render_queue_lock.release()

			if rscale != scale:
				# Queue a render at the correct scale
				self._queue_page_render_at_scale(page, scale)
			return result, rscale
		except KeyError:
			# Nothing, there, queue the rendering
			self._render_queue_lock.release()
			self._queue_page_render_at_scale(page, scale)
			return None

	def emit_pdf(self, filename):
		self.sort_boxes()
		width, height = self.document.get_page(0).get_size()
		surface = cairo.PDFSurface(filename, width, height)
		cr = cairo.Context(surface)
		page = 0
		for box in self.iter_boxes():
			while box.dpage > page:
				page += 1
				cr.show_page()
			cr.save()
			cr.translate(+box.dx, +box.dy)
			cr.rectangle(0, 0, box.width, box.height)
			cr.clip()
			cr.translate(-box.sx, -box.sy)
			self.document.get_page(box.spage).render_for_printing(cr)
			cr.restore()

	def iter_boxes(self):
		for box in self._boxes:
			yield box

	def sort_boxes(self):
		self._boxes.sort()

	def add_box(self, box):
		ypos = _PADDING
		page = 0
		self._boxes.sort()
		for b in self._boxes:
			if b.dpage > page:
				page = b.dpage
				ypos = _PADDING
			ypos = max(ypos, b.dy + b.height)
		width, height = self.document.get_page(0).get_size()
		if ypos + box.height > height - _PADDING:
			page += 1
			ypos = _PADDING
		box.dy = ypos
		box.dpage = page

		self._boxes.append(box)
		box._model = self
		self.emit("box-added", box)

	def remove_box(self, box):
		self._boxes.remove(box)
		self.emit("box-removed", box)

	def save_to_file(self, filename):
		f = open(filename, 'w')
		f.write('PdfCutter File\n')
		f.write(self.pdffile)
		f.write('\n')
		for b in self._boxes:
			f.write("%f %f %f %f %f %f %i %i\n" % (b.sx, b.sy, b.width, b.height, b.dx, b.dy, b.spage, b.dpage))

	def _load_from_file(self):
		f = open(self.loadfile, "r")
		assert(f.readline() == 'PdfCutter File\n')
		self.pdffile = f.readline()[:-1]
		for line in f.readlines():
			data = line.split()
			b = Box()
			b.sx = float(data[0])
			b.sy = float(data[1])
			b.width = float(data[2])
			b.height = float(data[3])
			b.dx = float(data[4])
			b.dy = float(data[5])
			b.spage = int(data[6])
			b.dpage = float(data[7])
			b._model = self
			self._boxes.append(b)

	def _queue_box_render_at_scale(self, box, scale):
		self._render_queue_lock.acquire()
		for queue in self._box_render_queue:
			if queue[0] != box:
				continue

			if queue[1] != scale:
				self._box_render_queue.remove(queue)
			else:
				self._render_queue_lock.release()
				return
					
		self._box_render_queue.append((box, scale))
		# Recreate thread if neccessary
		if not self._render_thread_running:
			thread.start_new_thread(self._render_thread, ())
			self._render_thread_running = True
		self._render_queue_lock.release()

	def _queue_page_render_at_scale(self, page, scale):
		self._render_queue_lock.acquire()

		for queue in self._page_render_queue:
			if queue[0] == page:
				if queue[1] != scale:
					self._page_render_queue.remove(queue)
				else:
					self._render_queue_lock.release()
					return

		self._page_render_queue.append((page, scale))
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

		page = self.document.get_page(page_number)
		scaled_width = width + 1
		scaled_height = height + 1
		scaled_width = scaled_width * scale
		scaled_height = scaled_height * scale
		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(math.ceil(scaled_width)), int(math.ceil(scaled_height)))
		cr = cairo.Context(surface)
		cr.set_source_rgba(0, 0, 0, 0)
		cr.set_operator(cairo.OPERATOR_SOURCE)
		cr.paint()

		cr.set_operator(cairo.OPERATOR_OVER)
		cr.translate(-math.ceil(x), -math.ceil(y))
		cr.scale(scale, scale)
		page.render(cr)

		self._render_queue_lock.acquire()
		self._rendered_boxes[box] = (surface, scale, page_number, x, y, width, height, x - math.ceil(x), y - math.ceil(y))
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

		page = self.document.get_page(page_number)
		width, height = page.get_size()
		width *= scale
		height *= scale
		surface = cairo.ImageSurface(cairo.FORMAT_RGB24, int(width), int(height))
		cr = cairo.Context(surface)
		cr.set_source_rgba(1, 1, 1)
		cr.paint()

		cr.scale(scale, scale)
		page.render(cr)

		self._render_queue_lock.acquire()
		self._rendered_pages[page_number] = (surface, scale)
		self._render_queue_lock.release()

		gobject.idle_add(self._emit_page_rendered, page_number)

