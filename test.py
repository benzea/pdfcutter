#! /usr/bin/env python

import gobject
import gtk
import poppler
import model
import pdfview
import goocanvas
from pdfview import PDFView

gtk.gdk.threads_init()

gtk.gdk.threads_enter()
win = gtk.Window(gtk.WINDOW_TOPLEVEL)

scroll = gtk.ScrolledWindow()

win.add(scroll)

mod = model.Model("file:///home/benjamin/Desktop/presentacion_educativa_caf_fondo-2-en.pdf")

box = model.Box()
box.width = 100
box.height = 100
box.page = 1
mod.add_box(box)

canvas = PDFView()
canvas.set_model(mod)
canvas.set_scale(0.5)

scroll.add(canvas)

win.show_all()

def test():
#    box = model.Box()
#    box.x = 30
#    box.width = 100
#    box.height = 100
#    mod.add_box(box)
     canvas.set_scale(1.0)

gobject.timeout_add(5000, test)

gtk.main()
gtk.gdk.threads_leave()

