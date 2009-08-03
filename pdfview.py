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
import gtk
import goocanvas
import gobject

_BOX = 1
_EDGE_TOP = 2
_EDGE_BOTTOM = 4
_EDGE_LEFT = 8
_EDGE_RIGHT = 16

class Box(goocanvas.ItemSimple, goocanvas.Item):
	__gtype_name__ = "PDFViewBox"
	_LINE_WIDTH = 2
	def __init__(self, canvas, box, **kwargs):
		super(Box, self).__init__(**kwargs)
		self._canvas = canvas
		self._box = box
		self.x = 0
		self.y = 0
		self.width = 1
		self.height = 1
		
		self._drag_active = False

		self.update_pos()

	def do_simple_create_path(self, cr):
		cr.rectangle(self.x, self.y, self.width, self.height)

	def do_simple_is_item_at(self, x, y, cr, is_pointer_event):
		if self.x <= x and self.x + self.width >= x and \
		   self.y <= y and self.y + self.height >= y:
			return True
		return False

	def update_pos(self):
		self._canvas.request_redraw(self.bounds)
		page = self._canvas._pages[self._box.page]
		self.x = self._box.x
		self.y = self._box.y
		self.width = self._box.width
		self.height = self._box.height
		self.x += page.x
		self.y += page.y

		self.bounds_x1 = self.x
		self.bounds_x2 = self.x + self.width
		self.bounds_y1 = self.y
		self.bounds_y2 = self.y + self.height

		self._canvas.request_update()
		self._canvas.request_redraw(self.bounds)

	def do_button_press_event(self, target, event):
		if event.button == 1:
			if event.state & gtk.gdk.CONTROL_MASK:
				self._canvas._model.remove_box(self._box)
				return True

			self._drag_active = True
			
			self._mouse_x = event.x
			self._mouse_y = event.y
			x = self._mouse_x
			y = self._mouse_y
			x -= self.x
			y -= self.y

			self._drag = 0
			if y <= self._LINE_WIDTH * 2:
				self._drag |= _EDGE_TOP
			if self.height - y <= self._LINE_WIDTH * 2:
				self._drag |= _EDGE_BOTTOM
			if x <= self._LINE_WIDTH * 2:
				self._drag |= _EDGE_LEFT
			if self.width - x <= self._LINE_WIDTH * 2:
				self._drag |= _EDGE_RIGHT

			if self._drag == 0:
				self._drag = _BOX

	def do_button_release_event(self, target, event):
		if event.button == 1 and self._drag_active:
			self._drag_active = False

	def do_motion_notify_event(self, target, event):
		if not self._drag_active:
			return False

		dx = event.x - self._mouse_x
		dy = event.y - self._mouse_y
		max_x = self._canvas._pages[self._box.page].width
		max_y = self._canvas._pages[self._box.page].height

		if self._drag == _BOX:
			new_x = self._box.x + dx
			new_y = self._box.y + dy

			self._box.x = max(0, min(new_x, max_x - self._box.width))
			self._box.y = max(0, min(new_y, max_y - self._box.height))

			dx -= new_x - self._box.x
			dy -= new_y - self._box.y
		if self._drag & _EDGE_TOP:
			dy = min(dy, self._box.height - 5)
			if self._box.y + dy < 0:
				dy = -self._box.y

			self._box.y = self._box.y + dy
			self._box.height = self._box.height - dy
		if self._drag & _EDGE_BOTTOM:
			dy = max(-self._box.height + 5, dy)
			dy = min(dy, max_y - self._box.height - self._box.y)

			self._box.height += dy
		if self._drag & _EDGE_LEFT:
			dx = min(dx, self._box.width - 5)
			if self._box.x + dx < 0:
				dx = -self._box.x

			self._box.x = self._box.x + dx
			self._box.width = self._box.width - dx
		if self._drag & _EDGE_RIGHT:
			dx = max(-self._box.width + 5, dx)
			dx = min(dx, max_x - self._box.width - self._box.x)

			self._box.width += dx

		self._mouse_x += dx
		self._mouse_y += dy

		return True

	def do_simple_paint(self, cr, bounds):
		pass

	def do_paint(self, cr, bounds, scale):
		lw = self._LINE_WIDTH
		cr.set_line_width(lw)
		cr.rectangle(self.x + lw/2, self.y + lw/2, self.width - lw, self.height - lw)
		cr.set_source_rgba(1.0, 0, 0, 0.8)
		cr.stroke()

class Page(goocanvas.ItemSimple, goocanvas.Item):
	__gtype_name__ = "PDFViewPage"
	
	def __init__(self, model, page, x, y, **kwargs):
		super(Page, self).__init__(**kwargs)
		self.x = x
		self.y = y
		self._page = page
		self._model = model
		self.width, self.height = model.document.get_page(page).get_size()

	def do_simple_is_item_at(self, x, y, cr, is_pointer_event):
		if self.x <= x and self.x + self.width >= x and \
		   self.y <= y and self.y + self.height >= y:
			return True
		return False

	def do_simple_create_path(self, cr):
		cr.rectangle(self.x - 2, self.y - 2, self.width + 4, self.height + 4)

	def do_simple_paint(self, cr, bounds):
		pass

	def do_paint(self, cr, bounds, scale):
		if ( bounds.x1 > self.x + self.width + 2 or \
		     bounds.y1 > self.y + self.height + 2 ) or \
		   ( bounds.x2 < self.x - 2 or bounds.y2 < self.y - 2 ):
			return

		cr.save()
		cr.set_source_rgb(0.3, 0.3, 0.3)
		cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
		cr.rectangle(self.x-1, self.y-1, self.width+2, self.height+2)
		cr.rectangle(self.x+1, self.y+1, self.width-2, self.height-2)
		cr.fill()

		result = self._model.get_rendered_page_or_queue(self._page, scale)
		if result is None:
			cr.translate(self.x + self.width / 2.0, self.y + self.height / 2.0)
			cr.set_source_rgb(0.4, 0.4, 0.4)
			extends = cr.text_extents("Loading ...")

			height = extends[3]
			width = extends[4]
			scale = (self.width * 0.8) / width
			cr.translate(- width * scale / 2.0 - extends[0] * scale, - height * scale / 2.0 - extends[1] * scale)
			cr.scale(scale, scale)

			cr.move_to(0, 0)
			cr.show_text("Loading ...")
			cr.restore()
			return

		image = result[0]
		iscale = result[1]
		cr.translate(self.x, self.y)
		cr.scale(1 / iscale, 1 / iscale)
		cr.set_source_surface(image)
		cr.paint()

		cr.restore()
			
	def do_button_press_event(self, target, event):
		pass


class PDFView(goocanvas.Canvas):
	__gtype_name__ = 'PDFView'

	def __init__(self):
		# Pass __init__ up
		goocanvas.GroupModel.__init__(self)
		self._model = None
		self._root = self.get_root_item()
		self._pages = []
		self._boxes = {}
	
	def set_model(self, model):
		if self._model:
			self._model.disconnect(self._page_rendered_id)
			self._model.disconnect(self._box_changed_id)
			self._model.disconnect(self._box_added_id)
			self._model.disconnect(self._box_removed_id)

		self._model = model
		self._page_rendered_id = self._model.connect("page-rendered", self._page_rendered_cb)
		self._box_changed_id = self._model.connect("box-changed", self._box_changed_cb)
		self._box_added_id = self._model.connect("box-added", self._box_added_cb)
		self._box_removed_id = self._model.connect("box-removed", self._box_removed_cb)

		for page in self._pages:
			page.remove
		for box, dbox in self._boxes:
			dbox.remove
		self._pages = []
		self._boxes = {}

		PADDING = 5
		y = PADDING
		x = PADDING
		width = 0
		height = PADDING
		for i in xrange(self._model.document.get_n_pages()):
			page = Page(self._model, i, x, y, fill_color="black", parent=self._root)
			self._pages.append(page)

			y += PADDING
			y += page.height
			width = max(width, page.width)
			height += page.height + PADDING
		width = width + 2*PADDING

		self.set_bounds(0, 0, width, height)
		self.set_size_request(600, 450)

		for box in self._model.iter_boxes():
			self._boxes[box] = Box(self, box, parent=self._root)
	
	def get_model(self):
		return self._model

	model = gobject.property(type=object, setter=set_model, getter=get_model)

	def _page_rendered_cb(self, model, page):
		self.request_redraw(self._pages[page].get_bounds())

	def _box_changed_cb(self, model, box):
		self._boxes[box].update_pos()

	def _box_added_cb(self, model, box):
		self._boxes[box] = Box(self, box, parent=self._root)

	def _box_removed_cb(self, model, box):
		dbox = self._boxes.pop(box)
		dbox.remove()

