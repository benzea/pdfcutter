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
import model

_BOX = 1
_EDGE_TOP = 2
_EDGE_BOTTOM = 4
_EDGE_LEFT = 8
_EDGE_RIGHT = 16
_LINE_WIDTH = 2
_PADDING = 5

class Box(goocanvas.ItemSimple, goocanvas.Item):
	__gtype_name__ = "PDFBuildBox"
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
		page = self._canvas._pages[self._box.dpage]
		self.x = self._box.dx
		self.y = self._box.dy
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
			self._drag_active = True
			self._mouse_x = event.x
			self._mouse_y = event.y

	def do_button_release_event(self, target, event):
		if event.button == 1 and self._drag_active:
			self._drag_active = False

	def do_motion_notify_event(self, target, event):
		if not self._drag_active:
			return False

		max_x = self._canvas._pages[self._box.dpage].width
		max_y = self._canvas._pages[self._box.dpage].height

		if event.y < self._canvas._pages[self._box.dpage].y - _PADDING:
			if self._box.dpage > 0:
				self._box.dpage -= 1
				self._mouse_y -= _PADDING + max_y
		elif event.y > self._canvas._pages[self._box.dpage].y + \
		               self._canvas._pages[self._box.dpage].height + \
		               _PADDING:
			self._box.dpage += 1
			self._mouse_y += _PADDING + max_y

		dx = event.x - self._mouse_x
		dy = event.y - self._mouse_y

		new_x = self._box.dx + dx
		new_y = self._box.dy + dy

		self._box.dx = max(0, min(new_x, max_x - self._box.width))
		self._box.dy = max(0, min(new_y, max_y - self._box.height))

		dx -= new_x - self._box.dx
		dy -= new_y - self._box.dy

		self._mouse_x += dx
		self._mouse_y += dy

		return True

	def do_simple_paint(self, cr, bounds):
		pass

	def do_paint(self, cr, bounds, scale):
		if ( bounds.x1 > self.x + self.width + 2 or \
		     bounds.y1 > self.y + self.height + 2 ) or \
		   ( bounds.x2 < self.x - 2 or bounds.y2 < self.y - 2 ):
			return

		lw = _LINE_WIDTH
		cr.set_line_width(lw)
		cr.rectangle(self.x + lw/2, self.y + lw/2, self.width - lw, self.height - lw)
		cr.set_source_rgba(1.0, 0, 0, 0.8)
		cr.stroke()

		cr.save()

		result = self._canvas._model.get_rendered_box_or_queue(self._box, scale)
		if result is None:
			cr.translate(self.x + self.width / 2.0, self.y + self.height / 2.0)
			cr.set_source_rgb(0.4, 0.4, 0.4)
			extends = cr.text_extents("Loading ...")

			height = extends[3]
			width = extends[4]
			wscale = (self.width * 0.8) / width
			hscale = (self.height * 0.8) / height
			scale = min(hscale, wscale)
			cr.translate(- width * scale / 2.0 - extends[0] * scale, - height * scale / 2.0 - extends[1] * scale)
			cr.scale(scale, scale)

			cr.move_to(0, 0)
			cr.show_text("Loading ...")
			cr.restore()
			return

		image = result[0]
		iscale = result[1]
		offset_x = result[2]
		offset_y = result[3]
		cr.translate(self.x - offset_x, self.y - offset_y)
		cr.scale(1 / iscale, 1 / iscale)
		cr.set_source_surface(image)
		cr.rectangle(offset_x, offset_y, self._box.width, self._box.height)
		cr.fill()

		cr.restore()

class Page(goocanvas.ItemSimple, goocanvas.Item):
	__gtype_name__ = "PDFBuildPage"
	
	def __init__(self, model, page, x, y, **kwargs):
		super(Page, self).__init__(**kwargs)
		self.x = x
		self.y = y
		self._page = page
		self._model = model
		self.width, self.height = model.document.get_page(0).get_size()

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
		cr.rectangle(self.x, self.y, self.width, self.height)
		cr.fill()



class BuildView(goocanvas.Canvas):
	__gtype_name__ = 'BuildView'

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
		self._page_rendered_id = self._model.connect("box-rendered", self._box_rendered_cb)
		self._box_changed_id = self._model.connect("box-changed", self._box_changed_cb)
		self._box_added_id = self._model.connect("box-added", self._box_added_cb)
		self._box_removed_id = self._model.connect("box-removed", self._box_removed_cb)

		for page in self._pages:
			page.remove()
		for box, dbox in self._boxes.iteritems():
			dbox.remove()
		self._pages = []
		self._boxes = {}

		self._add_page()
		self.set_size_request(600, 450)

		for box in self._model.iter_boxes():
			while box.dpage + 1 > len(self._pages):
				self._add_page()
			self._boxes[box] = Box(self, box, parent=self._root)

	def _add_page(self):
		y = _PADDING
		x = _PADDING

		pwidth, pheight = self._model.document.get_page(0).get_size()

		y += (pheight + _PADDING) * len(self._pages)

		page = Page(self._model, len(self._pages), x, y, fill_color="black", parent=self._root)
		page.lower(None)
		self._pages.append(page)

		self.set_bounds(0, 0, pwidth + 2*_PADDING, (pheight + _PADDING) * len(self._pages) + _PADDING * 3)

	def _remove_page(self):
		self._pages.pop(len(self._pages) - 1).remove()

		pwidth, pheight = self._model.document.get_page(0).get_size()

		self.set_bounds(0, 0, pwidth + 2*_PADDING, (pheight + _PADDING) * len(self._pages) + _PADDING * 3)

	def _update_pages(self, min_pages=1):
		pages = min_pages
		for box in self._boxes.keys():
			pages = max(pages, box.dpage + 1)
		while pages > len(self._pages):
			self._add_page()
		while pages < len(self._pages):
			self._remove_page()

	def get_model(self):
		return self._model

	model = gobject.property(type=object, setter=set_model, getter=get_model)

	def _box_rendered_cb(self, model, box):
		try:
			self.request_redraw(self._boxes[box].get_bounds())
		except KeyError:
			# Just ignore if it the box disappeared already
			pass

	def _box_changed_cb(self, model, box):
		self._update_pages()
		self._boxes[box].update_pos()

	def _box_added_cb(self, model, box):
		self._update_pages(box.dpage + 1)
		self._boxes[box] = Box(self, box, parent=self._root)

	def _box_removed_cb(self, model, box):
		self._update_pages()
		dbox = self._boxes.pop(box)
		dbox.remove()

