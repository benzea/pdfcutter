#! /usr/bin/env python
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

import gobject
import gtk
import gtk.glade
import os
import time
import sys

from view_widget import ViewWidget
from model import Model, Box
from cutter import Cutter


zoom_steps = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]

class MainWindow(object):
	
	def __init__(self) :
		self._glade = gtk.glade.XML(os.path.join('./main_window.glade'))
		
		self._window = self._glade.get_widget("pdfcutter")
		self._glade.signal_autoconnect(self)
		self._window.maximize()

		scrolled_window = self._glade.get_widget("view_window")
		self._model = Model("file:///home/benjamin/Desktop/presentacion_educativa_caf_fondo-2-en.pdf")
		
		self.view = ViewWidget(self._model)
		scrolled_window.add(self.view)

		self.view.props.zoom = 1.0
		
		# So the buttons are insensitive
		self.update_ui()
		self._window.show_all()

	def update_ui(self):
		pages = self._model.document.get_n_pages()
		spin = self._glade.get_widget("page_spin")
		spin.set_range(1, pages)

	def on_page_spin_value_changed(self, spinbutton):
		self.view.props.page = spinbutton.get_value_as_int() - 1

	def on_zoom_out_clicked(self, button):
		cur_zoom = self.view.props.zoom
		try:
			i = zoom_steps.index(cur_zoom)
			i -= 1
			if i >= 0:
				self.view.props.zoom = zoom_steps[i]
		except:
			self.view.props.zoom = 1.0
	
	def on_build_pdf_clicked(self, button):
		cutter = Cutter(self._model)
		cutter.write_pdf("/tmp/test.pdf")

	def on_zoom_in_clicked(self, button):
		cur_zoom = self.view.props.zoom
		try:
			i = zoom_steps.index(cur_zoom)
			i += 1
			if i < len(zoom_steps):
				self.view.props.zoom = zoom_steps[i]
		except:
			self.view.props.zoom = 1.0

	def quit_application(self, *args):
		gtk.main_quit()

win = MainWindow()

gtk.main()

