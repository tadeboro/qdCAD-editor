import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

import math
import enum

import cairo

# Constants
GRID_UNIT = 50
HALF_GRID_UNIT = int(GRID_UNIT // 2)

class Cell(object):

    counter = 0

    class Type(enum.Enum):
        internal = "I"
        driver = "D"
        electrode = "E"
        output = "O"

    class Clock(enum.Enum):
        undefined = "U"
        switch = "S"
        hold = "H"
        release = "R"
        relax = "L"

    class Value(enum.Enum):
        n = "N"
        a = "A"
        b = "B"
        c = "C"
        d = "D"

    def __init__(self, x, y, z, type, clock, value):
        self.x = x
        self.y = y
        self.z = z
        self.type = type
        self.clock = clock
        self.value = value
        if type == Cell.Type.electrode:
            self.id = Cell.counter
            Cell.counter += 1

    @property
    def qdstruct_format(self):
        return "T {} {} {} {} {} {}".format(
            self.type.value, self.x, self.y, self.z, self.clock.value,
            self.value.value
        )

    @classmethod
    def from_string(cls, string):
        _, type, x, y, z, clock, value = string.split()
        return cls(int(x), int(y), int(z),
                   Cell.Type(type), Cell.Clock(clock), Cell.Value(value))


class Point(object):

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __str__(self):
        return "Point({}, {})".format(self.x, self.y)


class App(object):

    def __init__(self):
        builder = Gtk.Builder()
        builder.add_from_file("qdcad-edit.glade")
        builder.connect_signals(self)

        self.window = builder.get_object("main-window")
        self.window.show_all()
        self.area = builder.get_object("draw-area")

        # Offset tracking
        self.offset = Point(HALF_GRID_UNIT, HALF_GRID_UNIT)
        self.offset_old = Point(0, 0)
        self.drag_start = Point(0, 0)
        self.drag_occured = False

        # Cells
        self.cells = dict()

        # GUI state
        self.layer = 0
        self.active_type = Cell.Type.internal
        self.active_clock = Cell.Clock.switch
        self.active_value = Cell.Value.n

        # Settings widgets
        names = ("no-cycles", "no-evals", "eps", "max-steps",
                 "influence-radius", "arch")
        self.sim_params = {name: builder.get_object(name) for name in names}

        # Inputs
        self.inputs = builder.get_object("inputs")

    def run(self):
        Gtk.main()

    # Helpers
    def _to_cell_coords(self, x, y):
        return (int((x - self.offset.x + HALF_GRID_UNIT) // GRID_UNIT),
                int((y - self.offset.y + HALF_GRID_UNIT) // GRID_UNIT))

    def _from_cell_coords(self, x, y):
        """
        Return center of cell in widget coordinates.
        """
        return x * GRID_UNIT + self.offset.x, y * GRID_UNIT + self.offset.y

    def _save_qdstruct(self, filename):
        with open(filename, "w") as f:
            f.write("{}\n".format(len(self.cells)))
            f.write("{}\n".format(self.sim_params["arch"].get_text()))
            elec, oth = [], []
            for cell in self.cells.values():
                if cell.type == Cell.Type.electrode:
                    elec.append(cell)
                else:
                    oth.append(cell)
            elec.sort(key=lambda x: x.id)
            for cell in elec:
                f.write("{}\n".format(cell.qdstruct_format))
            for cell in oth:
                f.write("{}\n".format(cell.qdstruct_format))
            names = ("no-cycles", "no-evals", "eps",
                     "max-steps", "influence-radius")
            for name in names:
                f.write("{}\n".format(self.sim_params[name].get_text()))
            text = self.inputs.props.text.strip()
            if not text:
                f.write("0\n")
            else:
                f.write("{}\n".format(len(text.split("\n"))))
                f.write("{}\n".format(text))

    def _load_qdstruct(self, filename):
        with open(filename, "r") as f:
            lines = [line.strip() for line in f.readlines()
                     if line.strip() and line.strip()[0] != "%"]

        no_cells = int(lines.pop(0))
        self.sim_params["arch"].set_text(lines.pop(0))
        self.cells = {}
        for _ in range(no_cells):
            cell = Cell.from_string(lines.pop(0))
            self.cells[(cell.x, cell.y, cell.z)] = cell
        names = ("no-cycles", "no-evals", "eps",
                 "max-steps", "influence-radius")
        for name in names:
            self.sim_params[name].set_text(lines.pop(0))
        no_inputs = int(lines.pop(0))
        text = ""
        for _ in range(no_inputs):
            text += lines.pop(0) + "\n"
        self.inputs.props.text = text
        self.area.queue_draw()

    def _save_pdf(self, filename):
        if len(self.cells) == 0:
            return

        x_min, y_min, _ = next(iter(self.cells.keys()))
        x_max, y_max = x_min, y_min
        for x, y, _ in self.cells.keys():
            x_min = x_min if x_min < x else x
            x_max = x_max if x_max > x else x
            y_min = y_min if y_min < y else y
            y_max = y_max if y_max > y else y

        width  = (x_max + 1 - x_min) * GRID_UNIT
        height = (y_max + 1 - y_min) * GRID_UNIT
        surface = cairo.PDFSurface(filename, width, height)
        cr = cairo.Context(surface)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.translate(-x_min * GRID_UNIT, -y_min * GRID_UNIT)
        backup_offset = self.offset
        self.offset = Point(HALF_GRID_UNIT, HALF_GRID_UNIT)
        self._draw_cells(cr, self.layer)
        self.offset = backup_offset


    # Callbacks
    def on_delete(*_):
        # TODO: Ask for save?
        Gtk.main_quit()

    def on_save(self, *_):
        filter = Gtk.FileFilter()
        filter.set_name("qdCAD documents")
        filter.add_pattern("*.qdStruct")

        dialog = Gtk.FileChooserDialog("Save", self.window,
                                       Gtk.FileChooserAction.SAVE,
                                       ("Save", Gtk.ResponseType.OK,
                                        "Cancel", Gtk.ResponseType.CANCEL))
        dialog.add_filter(filter)

        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if not filename.endswith(".qdStruct"):
                filename += ".qdStruct"
            self._save_qdstruct(filename)
        dialog.destroy()

    def on_load(self, *_):
        filter = Gtk.FileFilter()
        filter.set_name("qdCAD documents")
        filter.add_pattern("*.qdStruct")

        dialog = Gtk.FileChooserDialog("Open", self.window,
                                       Gtk.FileChooserAction.OPEN,
                                       ("Open", Gtk.ResponseType.OK,
                                        "Cancel", Gtk.ResponseType.CANCEL))
        dialog.add_filter(filter)

        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            self._load_qdstruct(filename)
        dialog.destroy()

    def on_export(self, *_):
        filter = Gtk.FileFilter()
        filter.set_name("PDF documents")
        filter.add_pattern("*.pdf")

        dialog = Gtk.FileChooserDialog("Export", self.window,
                                       Gtk.FileChooserAction.SAVE,
                                       ("Export", Gtk.ResponseType.OK,
                                        "Cancel", Gtk.ResponseType.CANCEL))
        dialog.add_filter(filter)

        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if not filename.endswith(".pdf"):
                filename += ".pdf"
            self._save_pdf(filename)
        dialog.destroy()

    def on_draw(self, _, cr):
        _, clip = Gdk.cairo_get_clip_rectangle(cr)

        self._draw_grid(cr, clip)
        self._draw_cells(cr, self.layer)
        return True

    def on_button_press(self, _, event):
        if event.button == 1:
            self.drag_start = Point(event.x, event.y)
            self.offset_old = self.offset

        return False

    def on_button_release(self, widget, event):
        x, y = self._to_cell_coords(event.x, event.y)
        z = self.layer

        if event.button == 3 and (x, y, z) in self.cells:
            del self.cells[(x, y, z)]
            widget.queue_draw()
            return True

        if event.button == 1:
            if not self.drag_occured:
                self.cells[(x, y, z)] = Cell(x, y, z, self.active_type,
                                             self.active_clock,
                                             self.active_value)
                widget.queue_draw()
            self.drag_occured = False
            return True

        return False

    def on_motion(self, widget, event):
        self.drag_occured = True
        self.offset = Point(
            int(event.x - self.drag_start.x + self.offset_old.x),
            int(event.y - self.drag_start.y + self.offset_old.y)
        )
        widget.queue_draw()
        return True

    # Type changers
    def on_electrode(self, widget):
        self._change_type(widget, Cell.Type.electrode)

    def on_driver(self, widget):
        self._change_type(widget, Cell.Type.driver)

    def on_internal(self, widget):
        self._change_type(widget, Cell.Type.internal)

    def on_output(self, widget):
        self._change_type(widget, Cell.Type.output)

    # Clock changers
    def on_switch(self, widget):
        self._change_clock(widget, Cell.Clock.switch)

    def on_hold(self, widget):
        self._change_clock(widget, Cell.Clock.hold)

    def on_release(self, widget):
        self._change_clock(widget, Cell.Clock.release)

    def on_relax(self, widget):
        self._change_clock(widget, Cell.Clock.relax)

    def on_undefined(self, widget):
        self._change_clock(widget, Cell.Clock.undefined)

    # Value changers
    def on_value_n(self, widget):
        self._change_value(widget, Cell.Value.n)

    def on_value_a(self, widget):
        self._change_value(widget, Cell.Value.a)

    def on_value_b(self, widget):
        self._change_value(widget, Cell.Value.b)

    def on_value_c(self, widget):
        self._change_value(widget, Cell.Value.c)

    def on_value_d(self, widget):
        self._change_value(widget, Cell.Value.d)

    def on_switch_layer(self, adjustment):
        self.layer = int(adjustment.get_value())
        self.area.queue_draw()

    # Helpers
    def _change_type(self, widget, type):
        if widget.get_active():
            self.active_type = type

    def _change_clock(self, widget, clock):
        if widget.get_active():
            self.active_clock = clock

    def _change_value(self, widget, value):
        if widget.get_active():
            self.active_value = value

    def _draw_grid(self, cr, clip):
        cr.set_source_rgb(0.9333, 0.9333, 0.9255)
        cr.paint()

        x_min = (clip.x // GRID_UNIT * GRID_UNIT +
                 self.offset.x % GRID_UNIT - HALF_GRID_UNIT)
        x_max = clip.x + clip.width + GRID_UNIT

        y_min = (clip.y // GRID_UNIT * GRID_UNIT +
                 self.offset.y % GRID_UNIT - HALF_GRID_UNIT)
        y_max = clip.y + clip.height

        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(4)
        for x in range(x_min, x_max, GRID_UNIT):
            cr.move_to(x, clip.y)
            cr.line_to(x, y_max)
        for y in range(y_min, y_max, GRID_UNIT):
            cr.move_to(clip.x, y)
            cr.line_to(x_max, y)
        cr.stroke()

    def _draw_cells(self, cr, layer):
        # TODO: Layers need to be handled here
        for (x, y, z), cell in self.cells.items():
            if z == layer:
                self._draw_cell(cr, cell)

    def _draw_cell(self, cr, cell):
        value_lut = {
            Cell.Value.a: math.pi / 4,
            Cell.Value.b: math.pi / 4 * 3,
            Cell.Value.c: 0,
            Cell.Value.d: math.pi / 2,
        }
        clock_lut = {
            Cell.Clock.undefined: (0.6784, 0.4980, 0.6588),
            Cell.Clock.switch:    (0.9882, 0.9137, 0.3098),
            Cell.Clock.hold:      (0.4471, 0.6235, 0.8118),
            Cell.Clock.release:   (0.9882, 0.6863, 0.2431),
            Cell.Clock.relax:     (0.5412, 0.8863, 0.2039),
        }
        type_lut = {
            Cell.Type.internal:  (0.9333, 0.9333, 0.9255),
            Cell.Type.driver:    (0.3333, 0.3333, 0.3333),
            Cell.Type.electrode: (0.9373, 0.1608, 0.1608),
            Cell.Type.output:    (0.4588, 0.3137, 0.4824),
        }

        x, y = self._from_cell_coords(cell.x, cell.y)

        cr.save()
        cr.translate(x, y)

        cr.set_line_width(6)
        cr.rectangle(5 - HALF_GRID_UNIT, 5 - HALF_GRID_UNIT,
                     GRID_UNIT - 10, GRID_UNIT - 10)
        cr.set_source_rgb(*clock_lut[cell.clock])
        cr.fill_preserve()
        cr.set_source_rgb(*type_lut[cell.type])
        cr.stroke()

        if cell.type == Cell.Type.electrode:
            cr.move_to(5 - HALF_GRID_UNIT, HALF_GRID_UNIT - 5)
            cr.select_font_face("cairo:monospace", cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(20)
            cr.set_source_rgb(1, 1, 1)
            cr.show_text("{}".format(cell.id))

        cr.set_source_rgb(0, 0, 0)
        cr.new_sub_path()
        if cell.value == Cell.Value.n:
            cr.arc(0, 0, 3, 0, 2 * math.pi)
        else:
            cr.rotate(value_lut[cell.value])
            cr.arc( 10, 0, 5, 0, 2 * math.pi)
            cr.arc(-10, 0, 5, 0, 2 * math.pi)
        cr.fill()

        cr.restore()


if __name__ == "__main__":
    app = App()
    app.run()
