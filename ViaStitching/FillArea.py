#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#  FillArea.py
#
#  Copyright 2017 JS Reynaud <js.reynaud@gmail.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

from __future__ import print_function
from pcbnew import *
import sys
import getopt
import tempfile
import shutil
import os
import random
import pprint

"""
#  This script fills all areas of a specific net with Vias (Via Stitching)
#
#
# Usage in pcbnew's python console:
#  First you neet to copy this file (named FillArea.py) in your kicad_plugins
# directory (~/.kicad_plugins/ on Linux)
# Launch pcbnew and open python console (last entry of Tools menu)
# Then enter the following line (one by one, Hit enter after each)
import FillArea
FillArea.FillArea().Run()


# Other example:
# You can add modifications to parameters by adding functions calls:
FillArea.FillArea().SetDebug().SetNetname("GND").SetStepMM(1.27).SetSizeMM(0.6).SetDrillMM(0.3).SetClearanceMM(0.2).Run()

# with
# SetDebug: Activate debug mode (print evolution of the board in ascii art)
# SetNetname: Change the netname to consider for the filling
# (default is /GND or fallback to GND)
# SetStepMM: Change step between Via (in mm)
# SetSizeMM: Change Via copper size (in mm)
# SetDrillMM: Change Via drill hole size (in mm)
# SetClearanceMM: Change clearance for Via (in mm)

#  You can also use it in command line. In this case, the first parameter is
# the pcb file path. Default options are applied.

"""

class ViaObject:

    """
    ViaObject holds all information of a single Via
    """

    def __init__(self, x, y, pos_x, pos_y):
        self.X = x
        self.Y = y
        self.PosX = pos_x
        self.PosY = pos_y

class FillArea:

    """
    Automaticaly add via on area where there are no track/existing via,
    pads and keepout areas
    """

    REASON_OK           = 0
    REASON_NO_SIGNAL    = 1
    REASON_OTHER_SIGNAL = 2
    REASON_KEEPOUT      = 3
    REASON_TRACK        = 4
    REASON_PAD          = 5
    REASON_DRAWING      = 6
    REASON_STEP         = 7

    def __init__(self, filename=None):
        self.filename = None
        self.clearance = 0
        # Net name to use
        self.SetPCB(GetBoard())
        # Set the filename
        self.SetFile(filename)
        # Step between via
        self.SetStepMM(2.54)
        # Size of the via (diameter of copper)
        self.SetSizeMM(0.46)
        # Size of the drill (diameter)
        self.SetDrillMM(0.20)
        # Isolation between via and other elements
        # ie: radius from the border of the via
        self.SetClearanceMM(0.2)
        self.only_selected_area = False
        self.delete_vias = False
        if self.pcb is not None:
            for lnet in ["GND", "/GND"]:
                if self.pcb.FindNet(lnet) is not None:
                    self.SetNetname(lnet)
                    break
        self.netname = None
        self.debug = False
        self.random = False
        self.star = False
        if self.netname is None:
            self.SetNetname("GND")

        self.tmp_dir = None

    def SetFile(self, filename):
        self.filename = filename
        if self.filename:
            self.SetPCB(LoadBoard(self.filename))

    def SetDebug(self):
        self.debug = True
        return self

    def SetRandom(self):
        random.seed()
        self.random = True
        return self

    def SetStar(self):
        self.star = True
        return self

    def SetPCB(self, pcb):
        self.pcb = pcb
        if self.pcb is not None:
            self.pcb.BuildListOfNets()
        return self

    def SetNetname(self, netname):
        self.netname = netname.upper()
        return self

    def SetStepMM(self, s):
        self.step = float(FromMM(s))
        return self

    def SetSizeMM(self, s):
        self.size = float(FromMM(s))
        return self

    def SetDrillMM(self, s):
        self.drill = float(FromMM(s))
        return self

    def OnlyOnSelectedArea(self):
        self.only_selected_area = True
        return self

    def DeleteVias(self):
        self.delete_vias = True
        return self

    def SetClearanceMM(self, s):
        self.clearance = float(FromMM(s))
        return self

    def ViaIsInsideAllowedArea(self, x, y):
      """
      Check if the via is inside the allowed area.
      """
      board = self.pcb.ComputeBoundingBox(True)
      clearance = self.clearance + self.size
      if (x >= board.GetRight() - clearance) or (x <= board.GetLeft() + clearance):
        return False
      elif (y >= board.GetBottom() - clearance) or (y <= board.GetTop() + clearance):
        return False
      else:
        return True

    def GetReasonSymbol(self, reason):
        if isinstance(reason, ViaObject):
            return "X"
        if reason == self.REASON_NO_SIGNAL:
            return " "
        if reason == self.REASON_OTHER_SIGNAL:
            return "O"
        if reason == self.REASON_KEEPOUT:
            return "K"
        if reason == self.REASON_TRACK:
            return "T"
        if reason == self.REASON_PAD:
            return "P"
        if reason == self.REASON_DRAWING:
            return "D"
        if reason == self.REASON_STEP:
            return "-"

        return str(reason)

    def PrintRect(self, rectangle):
        """debuging tool
        Print board in ascii art
        """
        print("_" * (len(rectangle)+2))
        for y in range(len(rectangle[0])):
            print("|", end='')
            for x in range(len(rectangle)):
                print("%s" % self.GetReasonSymbol(rectangle[x][y]), end='')
            print("|")
        print("_" * (len(rectangle)+2))
        print('''
OK           = 'X'
NO_SIGNAL    = ' '
OTHER_SIGNAL = 'O'
KEEPOUT      = 'K'
TRACK        = 'T'
PAD          = 'P'
DRAWING      = 'D'
STEP         = '-'
''')

    def AddVia(self, position, x, y):
        m = VIA(self.pcb)
        m.SetPosition(position)
        m.SetNet(self.pcb.FindNet(self.netname))
        m.SetViaType(VIA_THROUGH)
        m.SetDrill(int(self.drill))
        m.SetWidth(int(self.size))
        #m.SetTimeStamp(33)  # USE 33 as timestamp to mark this via as generated
        self.pcb.Add(m)

    def RefillBoardAreas(self):
        for i in range(self.pcb.GetAreaCount()):
            area = self.pcb.GetArea(i)
            area.ClearFilledPolysList()
            area.UnFill()
            # Could not repair this.
            #if not area.GetIsKeepout():
              #area.BuildFilledSolidAreasPolygons(self.pcb)

    def CheckViaInAllAreas(self, via, all_areas):
        '''
        Checks if an existing Via collides with another area
        '''
        # Enum all area
        for area in all_areas:
            area_layer                  = area.GetLayer()
            area_clearance              = area.GetClearance()
            area_priority               = area.GetPriority()
            is_keepout_area             = area.GetIsKeepout()
            is_target_net               = (area.GetNetname().upper() == self.netname)

            if (not is_target_net):                                                         # Only process areas that are not in the target net
                offset = max(self.clearance, area_clearance) + self.size / 2                # Offset is half the size of the via plus the clearance of the via or the area
                for dx in [-offset, offset]:
                    for dy in [-offset, offset]:                                            # All 4 corners of the via are testet (upper, lower, left, right) but not the center
                        point_to_test   = wxPoint(via.PosX + dx, via.PosY + dy)

                        hit_test_area   = area.HitTestFilledArea(point_to_test)             # Collides with a filled area
                        hit_test_edge   = area.HitTestForEdge(point_to_test, 1)                # Collides with an edge/corner
                        hit_test_zone   = area.HitTestInsideZone(point_to_test)             # Is inside a zone (e.g. KeepOut)

                        if is_keepout_area and (hit_test_area or hit_test_edge or hit_test_zone):
                            return self.REASON_KEEPOUT                                      # Collides with keepout

                        elif (hit_test_area or hit_test_edge):
                            return self.REASON_OTHER_SIGNAL                                 # Collides with another signal (e.g. on another layer)

                        elif hit_test_zone:
                            # Check if the zone is higher priority than other zones of the target net in the same point
                            target_areas_on_same_layer = filter(lambda x: ((x.GetPriority() > area_priority) and (x.GetLayer() == area_layer) and (x.GetNetname().upper() == self.netname)), all_areas)
                            for area_with_higher_priority in target_areas_on_same_layer:
                                if area_with_higher_priority.HitTestInsideZone(point_to_test):
                                    break                                                   # Area of target net has higher priority on this layer
                            else:
                                return self.REASON_OTHER_SIGNAL                             # Collides with another signal (e.g. on another layer)

        return self.REASON_OK

    def ClearViaInStepSize(self, rectangle, x, y, distance):
        '''
        Stepsize==0
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O

        Standard
            O   O   O   O   O

            O   O   O   O   O

            O   O   O   O   O

            O   O   O   O   O

        Star
            O   O   O   O   O
              O   O   O   O
            O   O   O   O   O
              O   O   O   O
            O   O   O   O   O
              O   O   O   O
            O   O   O   O   O
        '''
        for x_pos in range(x-distance, x+distance+1):
            if (x_pos >= 0) and (x_pos < len(rectangle)):
                distance_y = distance-abs(x-x_pos) if self.star else distance       # Star or Standard shape
                for y_pos in range(y-distance_y, y+distance_y+1):
                    if (y_pos >= 0) and (y_pos < len(rectangle[0])):
                        if (x_pos == x) and (y_pos == y):
                            continue
                        rectangle[x_pos][y_pos] = self.REASON_STEP

    def Run(self):
        """
        Launch the process
        """

        if self.delete_vias:
            target_tracks = filter(lambda x: (x.GetNetname().upper() == self.netname), self.pcb.GetTracks())
            for via in target_tracks:
                if via.Type() == PCB_VIA_T:
                    if via.GetTimeStamp() == 33:
                        self.pcb.RemoveNative(via)
            self.RefillBoardAreas()
            if self.filename:
                self.pcb.Save(self.filename)
            return                                          # no need to run the rest of logic

        lboard = self.pcb.ComputeBoundingBox(True)
        origin = lboard.GetPosition()

        # Create an initial rectangle: all is set to "REASON_NO_SIGNAL"
        # get a margin to avoid out of range
        l_clearance = self.clearance + self.size
        x_limit     = int((lboard.GetWidth() + l_clearance) / l_clearance) + 1
        y_limit     = int((lboard.GetHeight() + l_clearance) / l_clearance) + 1

        rectangle = [[self.REASON_NO_SIGNAL]*y_limit for i in range(x_limit)]

        all_pads        = self.pcb.GetPads()
        all_tracks      = self.pcb.GetTracks()
        all_drawings    = filter(lambda x: x.GetClass() == 'PTEXT' and self.pcb.GetLayerID(x.GetLayerName()) in (F_Cu, B_Cu), self.pcb.DrawingsList())
        all_areas       = [self.pcb.GetArea(i) for i in range(self.pcb.GetAreaCount())]
        target_areas    = filter(lambda x: (x.GetNetname().upper() == self.netname), all_areas)         # KeepOuts are filtered because they have no name

        via_list = []       # Create a list of existing vias => faster than scanning through the whole rectangle
        max_target_area_clearance = 0

        # Enum all target areas (Search possible positions for vias on the target net)
        for area in target_areas:
            print ("Processing Target Area: %s, LayerName: %s..." % (area.GetNetname(), area.GetLayerName()))

            is_selected_area    = area.IsSelected()
            area_clearance      = area.GetClearance()
            if max_target_area_clearance < area_clearance:
                max_target_area_clearance = area_clearance

            if (not self.only_selected_area) or (self.only_selected_area and is_selected_area):         # All areas or only the selected area
                for x in range(len(rectangle)):                                                        # Check every possible point in the virtual coordinate system
                    for y in range(len(rectangle[0])):
                        if rectangle[x][y] == self.REASON_NO_SIGNAL:                                    # No other "target area" found yet => go on with processing
                            current_x = origin.x + (x * l_clearance)                                    # Center of the via
                            current_y = origin.y + (y * l_clearance)

                            # Sounds good doesn't work properly.
                            test_result = True                                                          # Start with true, if a check fails, it is set to false
                            offset = max(self.clearance, area_clearance) + self.size / 2                # Offset is half the size of the via plus the clearance of the via or the area
                            for dx in [-offset, offset]:
                                for dy in [-offset, offset]:                                            # All 4 corners of the via are testet (upper, lower, left, right) but not the center
                                    point_to_test   = wxPoint(current_x + dx, current_y + dy)
                                    # hit_test_area is only true if copper pour zones are filled
                                    hit_test_area   = area.HitTestFilledArea(point_to_test)             # Collides with a filled area
                                    hit_test_edge   = area.HitTestForEdge(point_to_test, 1)                # Collides with an edge/corner

                                    #print("Area", hit_test_area, "Edge", hit_test_edge)

                                    test_result &= hit_test_area and not hit_test_edge                  # test_result only remains true if the via is inside an area and not on an edge
                                    #test_result = hit_test_area

                            #print(test_result)
                            if self.ViaIsInsideAllowedArea(current_x, current_y) and test_result:
                            #if True:
                                via_obj = ViaObject(x=x, y=y, pos_x=current_x, pos_y=current_y)         # Create a via object with information about the via and place it in the rectangle
                                rectangle[x][y] = via_obj
                                via_list.append(via_obj)
        print(len(via_list))


        if self.debug:
            print("\nPost target areas:")
            self.PrintRect(rectangle)

        # Enum all vias
        print ("Processing all vias of target area...")
        for via in via_list:
            reason = self.CheckViaInAllAreas(via, all_areas)
            if reason != self.REASON_OK:
                rectangle[via.X][via.Y] = reason

        if self.debug:
            print("\nPost areas:")
            self.PrintRect(rectangle)

        # Same job with all pads => all pads on all layers
        print ("Processing all pads...")
        for pad in all_pads:
            local_offset = max(pad.GetClearance(), self.clearance, max_target_area_clearance) + (self.size / 2)
            max_size     = max(pad.GetSize().x, pad.GetSize().y)

            start_x      = int(floor(((pad.GetPosition().x - (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))
            stop_x       = int(ceil(((pad.GetPosition().x + (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))

            start_y      = int(floor(((pad.GetPosition().y - (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))
            stop_y       = int(ceil(((pad.GetPosition().y + (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))

            for x in range(start_x, stop_x + 1):
                for y in range(start_y, stop_y + 1):
                    if isinstance(rectangle[x][y], ViaObject):
                        start_rect = wxPoint(origin.x + (l_clearance * x) - local_offset,
                                            origin.y + (l_clearance * y) - local_offset)
                        size_rect = wxSize(2 * local_offset, 2 * local_offset)
                        if pad.HitTest(EDA_RECT(start_rect, size_rect), False):
                            rectangle[x][y] = self.REASON_PAD

        if self.debug:
            print("\nPost pads:")
            self.PrintRect(rectangle)

        # Same job with tracks => all tracks on all layers
        print ("Processing all tracks...")
        for track in all_tracks:
            start_x = track.GetStart().x
            start_y = track.GetStart().y

            stop_x = track.GetEnd().x
            stop_y = track.GetEnd().y

            if start_x > stop_x:
                d = stop_x
                stop_x = start_x
                start_x = d

            if start_y > stop_y:
                d = stop_y
                stop_y = start_y
                start_y = d

            osx = start_x
            osy = start_y
            opx = stop_x
            opy = stop_y

            clearance   = max(track.GetClearance(), self.clearance, max_target_area_clearance) + (self.size / 2) + (track.GetWidth() / 2)

            start_x     = int(floor(((start_x - clearance) - origin.x) / l_clearance))
            stop_x      = int(ceil(((stop_x + clearance) - origin.x) / l_clearance))

            start_y     = int(floor(((start_y - clearance) - origin.y) / l_clearance))
            stop_y      = int(ceil(((stop_y + clearance) - origin.y) / l_clearance))

            for x in range(start_x, stop_x + 1):
                for y in range(start_y, stop_y + 1):
                    if isinstance(rectangle[x][y], ViaObject):
                        start_rect = wxPoint(origin.x + (l_clearance * x) - clearance,
                                            origin.y + (l_clearance * y) - clearance)
                        size_rect = wxSize(2 * clearance, 2 * clearance)
                        if track.HitTest(EDA_RECT(start_rect, size_rect), False):
                            rectangle[x][y] = self.REASON_TRACK

        if self.debug:
            print("\nPost tracks:")
            self.PrintRect(rectangle)

        # Same job with existing text
        print ("Processing all existing drawings...")
        for draw in all_drawings:
            inter   = float(self.clearance + self.size)
            bbox    = draw.GetBoundingBox()

            start_x = int(floor(((bbox.GetPosition().x - inter) - origin.x) / l_clearance))
            stop_x  = int(ceil(((bbox.GetPosition().x + (bbox.GetSize().x + inter)) - origin.x) / l_clearance))

            start_y = int(floor(((bbox.GetPosition().y - inter) - origin.y) / l_clearance))
            stop_y  = int(ceil(((bbox.GetPosition().y + (bbox.GetSize().y + inter)) - origin.y) / l_clearance))

            for x in range(start_x, stop_x + 1):
                for y in range(start_y, stop_y + 1):
                    rectangle[x][y] = self.REASON_DRAWING

        if self.debug:
            print("Post Drawings:")
            self.PrintRect(rectangle)

        print ("Remove vias to guarantee step size...")
        clear_distance = 0
        if self.step != 0.0:
            clear_distance = int((self.step+l_clearance) / l_clearance)       # How much "via steps" should be removed around a via (round up)

        for x in range(len(rectangle)):
            for y in range(len(rectangle[0])):
                if isinstance(rectangle[x][y], ViaObject):
                    if clear_distance:
                        self.ClearViaInStepSize(rectangle, x, y, clear_distance)

                    via     = rectangle[x][y]
                    ran_x   = 0
                    ran_y   = 0

                    if self.random:
                        ran_x = (random.random() * l_clearance / 2.0) - (l_clearance / 4.0)
                        ran_y = (random.random() * l_clearance / 2.0) - (l_clearance / 4.0)

                    print("Here!")
                    self.AddVia(wxPoint(via.PosX + ran_x, via.PosY + ran_y), via.X, via.Y)

        if self.debug:
            print("\nFinal result:")
            self.PrintRect(rectangle)

        self.RefillBoardAreas()

        if self.filename:
            self.pcb.Save(self.filename)
        print ("Done!")

def main(argv):
    help_msg = "python " + sys.argv[0] + "<FILENAME.kicad_pcb> <OPTIONS>\n\nOptions:\n\t-h print this help message\n\t-n or --netname=<NETNAME>\n\t-s or --step=<STEP_MM>\n\t-a or --size=<VIASIZE_MM>\n\t-d or --drill=<DRILL_MM>\n\t-c or --clearance<CLEARANCE_MM>\n\t-e or --erase"
    netname = "0"
    stepMM = 1.27
    sizeMM = 0.6
    drillMM = 0.3
    clearanceMM = 0.2
    filename = sys.argv[1]
    erase = False
    if filename in ["-h", "--help"]:
        print(help_msg)
        sys.exit(2)
    try:
        opts, args = getopt.getopt(sys.argv[2:],"hn:s:a:d:ce",["netname=", "step=", "size=", "drill=", "clearance=", "erase"])
    except getopt.GetoptError:
        print(help_msg)
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print(help_msg)
            sys.exit(0)
        elif opt in ("--netname", "-n"):
            netname = str(arg)
        elif opt in ("--step", "-s"):
            stepMM = float(arg)
        elif opt in ("--size", "-a"):
            size = float(arg)
        elif opt in ("--drill", "-d"):
            drillMM = float(arg)
        elif opt in ("--clearance", "-c"):
            clearanceMM = float(arg)
        elif opt in ("--erase", "-e"):
            erase = True
    if erase:
        # As soon as you have the erase flag it will just remove all vias
        FillArea(filename).SetNetname(netname).DeleteVias().Run()
    else:
        FillArea(filename).SetDebug().SetNetname(netname).SetStepMM(stepMM).SetSizeMM(sizeMM).SetDrillMM(drillMM).SetClearanceMM(clearanceMM).Run()
    sys.exit(0)

if __name__ == '__main__':
    main(sys.argv[0:])
