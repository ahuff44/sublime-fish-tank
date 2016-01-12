import sublime, sublime_plugin
from pprint import pprint
import random
import math
import itertools as itt


def plugin_loaded():
    global SETTINGS, VITALITY_CHANGE_MULTIPLIER, MIN_FISH_LENGTH, MAX_FISH_LENGTH, COLORS

    SETTINGS = sublime.load_settings("FishTank.sublime-settings")
    VITALITY_CHANGE_MULTIPLIER = SETTINGS.get("vitality_change_multiplier")
    MIN_FISH_LENGTH = SETTINGS.get("min_fish_length")
    MAX_FISH_LENGTH = SETTINGS.get("max_fish_length")
    COLORS = SETTINGS.get("colors")

class Point(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __ne__(self, other):
        return not (self == other)

    def __str__(self):
        return "(%d, %d)"%(self.x, self.y)
    __repr__ = __str__

    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, val):
        return Point(self.x * val, self.y * val)

    def __neg__(self):
        return self * -1

    def __iter__(self):
        yield self.x
        yield self.y

    def __hash__(self):
        return 293*self.x + self.y # 293 is prime, and hash(x) = x whenever x is an integer

    def as_region(self, view):
        index = view.text_point(self.y, self.x)
        return sublime.Region(index, index+1)

class Fish(object):
    RIGHT = Point(1, 0)
    LEFT  = Point(-1, 0)
    UP    = Point(0, -1)
    DOWN  = Point(0, 1)
    ALL_DIRECTIONS = [RIGHT, LEFT, UP, DOWN]
    NEXT_DIRECTIONS = {
        RIGHT: ([RIGHT]*6) + ([   UP]*3) + ([ DOWN]*3) + ([ LEFT]*1),
         LEFT: ([ LEFT]*6) + ([   UP]*3) + ([ DOWN]*3) + ([RIGHT]*1),
           UP: ([   UP]*6) + ([RIGHT]*3) + ([ LEFT]*3) + ([ DOWN]*1),
         DOWN: ([ DOWN]*6) + ([RIGHT]*3) + ([ LEFT]*3) + ([   UP]*1),
    }
    FISH_ID_STORE = 0

    @classmethod
    def gen_region_key(klass):
        klass.FISH_ID_STORE += 1
        return "fish_tank_%d"%klass.FISH_ID_STORE

    @classmethod
    def gen_colors(klass, length):
        global COLORS

        return [random.choice(COLORS) for _ in range(length)]

    def __init__(self, x, y):
        global MIN_FISH_LENGTH, MAX_FISH_LENGTH

        self.pos = Point(x, y)
        self.vitality = random.random()

        self.direction = random.choice(self.ALL_DIRECTIONS)
        self.region_key = self.gen_region_key()
        self.length = random.randint(MIN_FISH_LENGTH, MAX_FISH_LENGTH)
        self.colors = self.gen_colors(self.length)

    def step(self, view, edit):
        self.move()
        self.render(view, edit)
        self.modify_vitality()

    def move(self):
        if self.vitality >= random.random():
            # Move in the current direction if possible
            if self.is_valid_pos(self.pos + self.direction):
                self.pos += self.direction

            # change direction, weighted towards current direction
            self.direction = random.choice(self.NEXT_DIRECTIONS[self.direction])

    def render(self, view, edit):
        new_highlight_regions = list(map(
            lambda point: point.as_region(view),
            self.neighbors(self.pos) + [self.pos],
        ))

        tail_segments = [new_highlight_regions] + [
            view.get_regions(self.region_key+"_%d"%i)
            for i in range(0, self.length-2) # don't copy over the least recent segment (# length - 1)
        ]

        # erase old colors
        for i in range(self.length):
            view.erase_regions(self.region_key+"_%d"%i)

        # draw new colors
        for i, (regions, color) in enumerate(zip(tail_segments, self.colors)):
            view.add_regions(
                self.region_key+"_%d"%i,
                regions,
                color,
            )

    def modify_vitality(self):
        global VITALITY_CHANGE_MULTIPLIER

        self.vitality += random.uniform(
            - (self.vitality) * VITALITY_CHANGE_MULTIPLIER,
            (1 - self.vitality) * VITALITY_CHANGE_MULTIPLIER,
        )

    @classmethod
    def is_valid_pos(klass, pos):
        global TANK_WIDTH, TANK_HEIGHT

        x, y = pos
        return 0 <= x < TANK_WIDTH and 0 <= y < TANK_HEIGHT

    @classmethod
    def neighbors(klass, pos):
        return [pos + dpos for dpos in klass.ALL_DIRECTIONS if klass.is_valid_pos(pos + dpos)]

class FishTankCustomCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.show_input_panel(
            "How many fish?",
            "4",
            self.set_count, #on_done,
            None, #on_change,
            None, #on_cancel,
        )

    def set_count(self, count_str):
        self.window.run_command("fish_tank", {"count": int(count_str)})

class FishTankCommand(sublime_plugin.WindowCommand):
    def run(self, count=None, count_multiplier=None):
        global WAIT_CONTROLLER, ALL_FISH, TANK_HEIGHT, TANK_WIDTH
        WAIT_CONTROLLER = self.gen_wait_controller()

        self.window.active_view().run_command("duplicate_view_to_buffer", {"name": "FISH :D"})
        tank = self.window.active_view() # this is a different view than it was during the last line

        if (count is None) and (not count_multiplier is None):
            count = round((count_multiplier * tank.size()) / 250)
        elif (not count is None) and (not count_multiplier is None):
            raise ValueError("Arguments 'count' and 'count_multiplier' cannot both be passed to fish_tank")
            return

        ALL_FISH = []
        for _ in range(count):
            ALL_FISH.append(Fish(
                random.randint(0, TANK_WIDTH-1),
                random.randint(0, TANK_HEIGHT-1),
            ))

        print("Fish Tank created with %d fish."%count)

        tank.run_command("fish_tank_step")

    def gen_wait_controller(self):
        global SETTINGS

        cycle_length = SETTINGS.get("cycle_length")
        average_wait = SETTINGS.get("average_wait")
        max_wait_deviation = SETTINGS.get("max_wait_deviation")

        for t in itt.count():
            deviation_multiplier = math.sin(2.0*math.pi * (t*1.0/cycle_length))
            yield average_wait + max_wait_deviation * deviation_multiplier

class FishTankStepCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global ALL_FISH, WAIT_CONTROLLER

        # print("Fish vitality: ", end="")
        for fish in ALL_FISH:
            fish.step(self.view, edit)
            # print("%.2f"%fish.vitality, end=", ")
        # print()

        wait_time = next(WAIT_CONTROLLER)

        # print(wait_time)
        sublime.set_timeout(
            lambda: self.view.run_command("fish_tank_step"),
            wait_time,
        )

class DuplicateViewToBufferCommand(sublime_plugin.TextCommand):
    """ Duplicates the current view to a buffer, adds space padding,
        and adds word wrapping.

        Adapted from https://github.com/jonfinerty/sublime-snake """

    def run(self, edit, name, force_line_wrap=False):
        global TANK_HEIGHT, TANK_WIDTH

        template_view = self.view
        window = template_view.window()

        # grab current file info
        entire_file_region = sublime.Region(0, template_view.size())
        file_text = template_view.substr(entire_file_region)

        syntax     = template_view.settings().get('syntax')
        tab_size   = template_view.settings().get('tab_size')
        wrap_width = template_view.settings().get("wrap_width")
        word_wrap  = template_view.settings().get("word_wrap")

        # copy view and syntax
        tank_view = window.new_file()
        tank_view.set_scratch(True)
        tank_view.set_name(name)
        window.focus_view(tank_view)
        tank_view.insert(edit, 0, file_text.replace("\t", " "*tab_size))
        tank_view.set_syntax_file(syntax)

        # set word wrap to maximum line length, otherwise pain
        tank_view.settings().set("wrap_width", 0)
        tank_view.settings().set("word_wrap", False)

            # replace word wrap with newlines
        if force_line_wrap or word_wrap == True or word_wrap == "auto":
                if wrap_width == 0:
                    line_length = tank_view.viewport_extent()[0]
                    wrap_width = int(line_length / tank_view.em_width())

                # these variables will be redefined later
                entire_tank_region = sublime.Region(0, tank_view.size())
                lines = tank_view.split_by_newlines(entire_tank_region)

                adjustment = 0
                for line in lines:
                    position = wrap_width
                    while position < line.size():
                        tank_view.insert(edit, line.a + position, "\n")
                        adjustment += 1
                        position += wrap_width

        # Determine tank dimensions
        # entire_tank_region and lines are redefined from earlier, when turning word_wrap off
        entire_tank_region = sublime.Region(0, tank_view.size())
        lines = tank_view.split_by_newlines(entire_tank_region)
        # print(tank_view.size(), lines)
        TANK_WIDTH = max(map(lambda line: line.size(), lines))
        TANK_HEIGHT = len(lines)

        # pad lines with spaces
        adjustment = 0 # keep track of how many characters we've added during this process
        for line in lines:
            padding_size = TANK_WIDTH - line.size()
            padding_string = " " * padding_size
            tank_view.insert(
                edit,
                line.b + adjustment,
                padding_string
            )
            adjustment += padding_size
