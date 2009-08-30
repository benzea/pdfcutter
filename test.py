#! /usr/bin/env python

import gobject
import gtk
import poppler
import model
import pdfview
import goocanvas
from pdfview import PDFView
from buildview import BuildView

gtk.gdk.threads_init()

gtk.gdk.threads_enter()
win = gtk.Window(gtk.WINDOW_TOPLEVEL)

mod = model.Model("file:///home/benjamin/Desktop/presentacion_educativa_caf_fondo-2-en.pdf")

box = model.Box()
box.width = 100
box.height = 100
box.page = 1
mod.add_box(box)

canvas = PDFView()
canvas.set_model(mod)
canvas.set_scale(1)

scroll = gtk.ScrolledWindow()
scroll.add(canvas)

hbox = gtk.HBox()
hbox.add(scroll)

canvas = BuildView()
canvas.set_model(mod)
canvas.set_scale(1)

scroll = gtk.ScrolledWindow()
scroll.add(canvas)

hbox.add(scroll)

win.add(hbox)
win.show_all()


gtk.main()
gtk.gdk.threads_leave()

