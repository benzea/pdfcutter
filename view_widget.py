# -*- coding: utf-8 -*-
# PDFCutter
# This is based on the sheet widget from SDAPS.
#
# Copyright (C) 2007-2008, Christoph Simon <christoph.simon@gmx.eu>
# Copyright (C) 2007-2009, Benjamin Berg <benjamin@sipsolutions.net>
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

import math
import gtk
import cairo
import gobject
import copy
import os
import poppler
from model import Model, Box

class ViewWidget(gtk.DrawingArea):
	_LEFT = 1
	_RIGHT = 2
	_TOP = 4
	_BOTTOM = 8

	__gtype_name__ = "ViewWidget"

	__gproperties__ = {
		'zoom'          : (float, None, None, 0.001, 1024.0, 1.0,
						   gobject.PARAM_READWRITE),
		'page'          : (int, None, None, 0, 1024, 10,
						   gobject.PARAM_READWRITE),
	}

	def __init__(self, model) :
		gtk.DrawingArea.__init__(self)
		self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK|
						gtk.gdk.MOTION_NOTIFY | gtk.gdk.SCROLL |
						gtk.gdk.KEY_PRESS_MASK)
		self.hadj = None
		self.vadj = None

		self._model = model
		self._document = self._model.document
		self._buffer = None

		self._old_scroll_x = 0
		self._old_scroll_y = 0
		self._edge_drag_active = False

		self._zoom = 1.0
		self._page = 0

		self.props.can_focus = True

		gobject.signal_new('set_scroll_adjustments', ViewWidget,
						   gobject.SIGNAL_NO_HOOKS, None, (gtk.Adjustment, gtk.Adjustment))
		self.set_set_scroll_adjustments_signal("set_scroll_adjustments")
		self.connect("set_scroll_adjustments", self.do_set_scroll_adjustments)

		self._update_matrices()

	def update_state(self):
		# Cancel any dragging operation
		self._edge_drag_active = False
		self.queue_resize()
		self._update_matrices()
		self._buffer = None
		self.queue_draw()

	def _update_matrices(self):
		xoffset = 0
		yoffset = 0
		if self.hadj:
			xoffset = int(self.hadj.value)
		if self.vadj:
			yoffset = int(self.vadj.value)

		m = cairo.Matrix(self._zoom, 0,
		                 0, self._zoom,
		                 -xoffset, -yoffset)

		self._pdf_to_widget_matrix = m
		self._widget_to_pdf_matrix = \
			cairo.Matrix(*m)
		self._widget_to_pdf_matrix.invert()

	def do_set_scroll_adjustments(dummy, self, hadj, vadj):
		self.hadj = hadj
		self.vadj = vadj

		if hadj:
			hadj.connect('value-changed', self._adjustment_changed_cb)
			self._old_scroll_x = hadj.value
		if vadj:
			vadj.connect('value-changed', self._adjustment_changed_cb)
			self._old_scroll_y = vadj.value
		return True

	def _adjustment_changed_cb(self, adjustment):
		dx = int(self._old_scroll_x) - int(self.hadj.value)
		dy = int(self._old_scroll_y) - int(self.vadj.value)

		self.window.scroll(dx, dy)

		self._old_scroll_x = self.hadj.value
		self._old_scroll_y = self.vadj.value

		# Update the transformation matrices
		self._update_matrices ()

	def find_box_at(self, x, y):
		for box in self._model.boxes:
			if box.page != self._page:
				continue

			if box.x <= x and box.x + box.width >= x and \
			   box.y <= y and box.y + box.height >= y:
				return box
		return None

	def do_button_press_event(self, event):
		# Pass everything except normal clicks down
		if event.button != 1 and event.button != 2 and event.button != 3:
			return False

		x, y = self._widget_to_pdf_matrix.transform_point(event.x, event.y)

		if event.button == 2:
			self._drag_start_x = event.x
			self._drag_start_y = event.y
			cursor = gtk.gdk.Cursor(gtk.gdk.HAND2)
			self.window.set_cursor(cursor)
			return True
			
		if event.button == 3:
			box = self.find_box_at(x, y)
			if box is not None:
				self._model.boxes.remove(box)
				self.queue_draw()
				return True

			return False

		# button 1
		self.grab_focus()

		# Look for edges to drag first (on a 4x4px target)
		tollerance_x, tollerance_y = self._widget_to_pdf_matrix.transform_distance(4.0, 4.0)
		object = None
		for box in self._model.boxes:
			if box.page != self._page:
				continue

			edge = 0
			if box.x - tollerance_x <= x and \
			   box.x + tollerance_x >= x and \
			   y >= box.y and y <= box.y + box.height:
				object = box
				edge = edge | self._LEFT

			if box.x + box.width - tollerance_x <= x and \
			   box.x + box.width + tollerance_x >= x and \
			   y >= box.y and y <= box.y + box.height:
				object = box
				edge = edge | self._RIGHT

			if box.y - tollerance_y <= y and \
			   box.y + tollerance_y >= y and \
			   x >= box.x and x <= box.x + box.width:
				object = box
				edge = edge | self._TOP

			if box.y + box.height - tollerance_y <= y and \
			   box.y + box.height + tollerance_y >= y and \
			   x >= box.x and x <= box.x + box.width:
				object = box
				edge = edge | self._BOTTOM

			if object is not None:
				break

		if object is not None:
			self._edge_drag_active = True
			self._edge_drag_obj = object
			self._edge_drag_edge = edge
			return True
		
		box = self.find_box_at(x, y)
		if box is not None:
			box.colored = not box.colored
			self.queue_draw()
			return True

		box = Box()
		box.page = self._page
		box.x = x
		box.y = y
		box.width = 10
		box.height = 10
		self._model.boxes.append(box)
		self._edge_drag_active = True
		self._edge_drag_obj = box
		self._edge_drag_edge = self._RIGHT | self._BOTTOM

		return True


	def do_button_release_event(self, event):
		if event.button != 1 and event.button != 2:
			return False

		self.window.set_cursor(None)

		if event.button == 1:
			self._edge_drag_active = False

		return True

	def do_motion_notify_event(self, event):
		if event.state & gtk.gdk.BUTTON2_MASK:
			x = int(event.x)
			y = int(event.y)

			dx = self._drag_start_x - x
			dy = self._drag_start_y - y

			if self.hadj:
				value = self.hadj.value + dx
				value = min(value, self.hadj.upper - self.hadj.page_size)
				self.hadj.set_value(value)
			if self.vadj:
				value = self.vadj.value + dy
				value = min(value, self.vadj.upper - self.vadj.page_size)
				self.vadj.set_value(value)

			self._drag_start_x = event.x
			self._drag_start_y = event.y

			return True
		elif event.state & gtk.gdk.BUTTON1_MASK:
			if self._edge_drag_active:
				x, y = self._widget_to_pdf_matrix.transform_point(event.x, event.y)
				
				page_width, page_height = self._document.get_page(self._page).get_size()

				box = self._edge_drag_obj
				if self._edge_drag_edge & self._LEFT:
					x = max(x, 1)
					new_width = max(10, box.width + box.x - x)
					x = box.x + (box.width - new_width)
			
					box.width = new_width
					box.x = x
				if self._edge_drag_edge & self._RIGHT:
					x = min(x, page_width)
					new_width = max(10, x - box.x)
					new_width = min(new_width, box.x + box.width)

					box.width = new_width
				if self._edge_drag_edge & self._TOP:
					y = max(y, 10)
					new_height = max(10, box.height + box.y - y)
					new_y = box.y + (box.height - new_height)
			
					box.height = new_height
					box.y = new_y
				if self._edge_drag_edge & self._BOTTOM:
					y = min(y, page_height)
					new_height = max(10, y - box.y)

					box.height = new_height

				self.queue_draw()
				return True

		return False


	def do_size_request(self, requisition):
		requisition[0] = self._render_width
		requisition[1] = self._render_height

		if self.hadj:
			self.hadj.props.upper = self._render_width
		if self.vadj:
			self.vadj.props.upper = self._render_height
		self.queue_draw()

	def do_size_allocate(self, allocation):
		if self.hadj:
			self.hadj.page_size = allocation.width
			self.hadj.page_increment = allocation.width * 0.9
			self.hadj.step_increment = allocation.width * 0.1
		if self.vadj:
			self.vadj.page_size = allocation.height
			self.vadj.page_increment = allocation.height * 0.9
			self.vadj.step_increment = allocation.height * 0.1

		self._update_matrices ()

		gtk.DrawingArea.do_size_allocate(self, allocation)

	def do_expose_event(self, event):
		cr = event.window.cairo_create()
		cr = gtk.gdk.CairoContext(cr)

		event.window.clear()
		# For the image
		xoffset = -int(self.hadj.value)
		yoffset = -int(self.vadj.value)

		# In theory we could get the region of the ExposeEvent, and only
		# draw on that area. The same goes for the image blitting.
		# However, pygtk does not expose the region attribute :-(
		#cr.region(event.region)
		rect = event.area
		cr.rectangle(rect.x, rect.y, rect.width, rect.height)
		cr.clip()

		if self._buffer is None:
			page = self._document.get_page(self._page)
			width, height = page.get_size()

			width = int(math.ceil(width * self._zoom))
			height = int(math.ceil(height * self._zoom))

			self._buffer = cr.get_target().create_similar(
				cairo.CONTENT_COLOR, width, height)
			subcr = cairo.Context(self._buffer)
			subcr.set_source_rgb(1, 1, 1)
			subcr.paint()
			subcr.scale(self._zoom, self._zoom)
			page = self._document.get_page(self._page)
			page.render(subcr)
			

		# Draw the pdf in the background
		cr.translate(xoffset, yoffset)
		cr.set_source_surface(self._buffer)
		cr.paint()

		cr.scale(self._zoom, self._zoom)

		for box in self._model.boxes:
			if box.page != self._page:
				continue
			cr.rectangle(box.x, box.y, box.width, box.height)
			if box.colored == False:
				cr.set_source_rgb(1, 0, 0)
			else:
				cr.set_source_rgb(0, 0, 1)
			cr.stroke()
		
		return True

	def do_key_press_event(self, event):
		if self.vadj:
			if event.keyval == gtk.gdk.keyval_from_name("Up"):
				value = self.vadj.value - self.vadj.step_increment
				value = min(value, self.vadj.upper - self.vadj.page_size)
				self.vadj.set_value(value)
				return True
			if event.keyval == gtk.gdk.keyval_from_name("Down"):
				value = self.vadj.value + self.vadj.step_increment
				value = min(value, self.vadj.upper - self.vadj.page_size)
				self.vadj.set_value(value)
				return True

		if self.hadj:
			if event.keyval == gtk.gdk.keyval_from_name("Left"):
				value = self.hadj.value - self.hadj.step_increment
				value = min(value, self.hadj.upper - self.hadj.page_size)
				self.hadj.set_value(value)
				return True
			if event.keyval == gtk.gdk.keyval_from_name("Right"):
				value = self.hadj.value + self.hadj.step_increment
				value = min(value, self.hadj.upper - self.hadj.page_size)
				self.hadj.set_value(value)
				return True
		return False

	def do_set_property(self, pspec, value):
		if pspec.name == 'zoom':
			self._zoom = value
			self.update_state()
		elif pspec.name == 'page':
			if value >= 0 and value < self._document.get_n_pages():
				self._page = value
				self.update_state()
			else:
				# XXX: Raise sane error
				raise AssertionError
		else:
			raise AssertionError

	def do_get_property(self, pspec):
		if pspec.name == 'zoom':
			return self._zoom
		elif pspec.name == 'page':
			return self._page
		else:
			raise AssertionError

	def _get_render_width(self):
		page = self._document.get_page(self._page)
		width, height = page.get_size()

		width = int(math.ceil(self._zoom * width))

		return width

	def _get_render_height(self):
		page = self._document.get_page(self._page)
		width, height = page.get_size()

		height = int(math.ceil(self._zoom * height))
		return height

	_render_width = property(_get_render_width)
	_render_height = property(_get_render_height)



