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

class Box(gobject.GObject):
	__gtype_name__ = 'PDFCutterBox'
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ([]))
	}
	def __init__(self):
		gobject.GObject.__init__(self)
		self._page = 0
		self._x = 0
		self._y = 0
		self._width = 0
		self._height = 0
		self._model = None
		
		# This can be true or false, ie. switches the "color" used
		# for layout purposes
		self.colored = False

	def get_x(self):
		return self._x
	def set_x(self, value):
		self._x = value
		self._emit_change()

	def get_y(self):
		return self._y
	def set_y(self, value):
		self._y = value
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

	def get_page(self):
		return self._page
	def set_page(self, value):
		self._page = value
		self._emit_change()

	def _emit_change(self):
		self.emit("changed")
		# so we do not need to connect to all the boxes in the model
		if self._model:
			self._model.emit("box-changed", self)

	x = gobject.property(type=float, getter=get_x, setter=set_x)
	y = gobject.property(type=float, getter=get_y, setter=set_y)
	width = gobject.property(type=float, getter=get_width, setter=set_width)
	height = gobject.property(type=float, getter=get_height, setter=set_height)
	page = gobject.property(type=int, getter=get_page, setter=set_page)

	def __cmp__(self, other):
		if self.page < other.page:
			return -1
		if self.page > other.page:
			return 1
		if self.y < other.y:
			return -1
		if self.y > other.y:
			return 1
		if self.x < other.x:
			return -1
		if self.x > other.x:
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

	def __init__(self, filename):
		gobject.GObject.__init__(self)

		self.filename = filename
		self.document = \
			poppler.document_new_from_file(self.filename, None)
		self._boxes = []
		self._rendered_boxes = {}
		self._rendered_pages = {}
		self._box_render_queue = []
		self._page_render_queue = []
		self._render_queue_lock = thread.allocate_lock()
		self._render_thread_running = False

	def get_rendered_box_or_queue (self, box, scale):
		try:
			# Try to retrieve a preprendered box
			rscale, result = self._rendered_boxes[box]

			if rscale != scale:
				# Queue a render at the correct scale
				self._queue_box_render_at_scale(self, box, scale)
			return result
		except KeyError:
			# Nothing, there, queue the rendering
			self._queue_box_render_at_scale(box, scale)
			return None
		
	def get_rendered_page_or_queue (self, page, scale):
		try:
			# Try to retrieve a preprendered box
			result, rscale = self._rendered_pages[page]

			if rscale != scale:
				# Queue a render at the correct scale
				self._queue_page_render_at_scale(page, scale)
			return result, rscale
		except KeyError:
			# Nothing, there, queue the rendering
			self._queue_page_render_at_scale(page, scale)
			return None

	def iter_boxes(self):
		for box in self._boxes:
			yield box

	def sort_boxes(self):
		self._boxes.sort()

	def add_box(self, box):
		self._boxes.append(box)
		box._model = self
		self.emit("box-added", box)

	def remove_box(self, box):
		self._boxes.remove(box)
		self.emit("box-removed", box)

	def _queue_box_render_at_scale(self, box, scale):
		self._render_queue_lock.acquire()
		for queue in self._box_render_queue:
			if queue[0] == box:
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
		pass

	def _emit_page_rendered(self, page):
		self.emit("page-rendered", page)
		return False

	def _render_page(self):
		self._render_queue_lock.acquire()
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
		cr.set_source_rgb(1, 1, 1)
		cr.paint()

		cr.scale(scale, scale)
		page.render(cr)

		self._rendered_pages[page_number] = (surface, scale)

		gobject.idle_add(self._emit_page_rendered, page_number)

