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

from gi.repository import GLib
import sys
import argparse
import threading
from model import Model

GLib.threads_init()

loop = GLib.MainLoop()

parser = argparse.ArgumentParser(description="Export PDF cutter content to PDF")

parser.add_argument('bcut', type=str, help="The pdfcutter file to export")
parser.add_argument('outfile', type=str, help="Export data to this file.")

args = parser.parse_args()
args = vars(args)

model = Model(loadfile=args['bcut'])

def wait(pos, count):
    if pos == count:
        loop.quit()

model.emit_pdf(args['outfile'], wait)

loop.run()

import time
time.sleep(0.5)
