import argparse
import time
import logging
from enum import Enum
import copy
import random
import PySimpleGUI as sg
from PIL import Image, ImageTk
import threading

from sympy import false


NUMBER_FONT = [
    [0xF0, 0x90, 0x90, 0x90, 0xF0],  # 0
    [0x20, 0x60, 0x20, 0x20, 0x70],  # 1
    [0xF0, 0x10, 0xF0, 0x80, 0xF0],  # 2
    [0xF0, 0x10, 0xF0, 0x10, 0xF0],  # 3
    [0x90, 0x90, 0xF0, 0x10, 0x10],  # 4
    [0xF0, 0x80, 0xF0, 0x10, 0xF0],  # 5
    [0xF0, 0x80, 0xF0, 0x90, 0xF0],  # 6
    [0xF0, 0x10, 0x20, 0x40, 0x40],  # 7
    [0xF0, 0x90, 0xF0, 0x90, 0xF0],  # 8
    [0xF0, 0x90, 0xF0, 0x10, 0xF0],  # 9
    [0xF0, 0x90, 0xF0, 0x90, 0x90],  # A
    [0xE0, 0x90, 0xE0, 0x90, 0xE0],  # B
    [0xF0, 0x80, 0x80, 0x80, 0xF0],  # C
    [0xE0, 0x90, 0x90, 0x90, 0xE0],  # D
    [0xF0, 0x80, 0xF0, 0x80, 0xF0],  # E
    [0xF0, 0x80, 0xF0, 0x80, 0x80],  # F
]

COMMAND_MASK = 0xF000

logging.basicConfig(level=logging.DEBUG)


class Chip8EMU(threading.Thread):
    def __init__(self, filename, processor_frequency=1e3):
        self.mem = [0]*4096
        self.stack = []
        self.delay_timer = 0
        self.sound_timer = 0
        self.PC = 512
        self.I = 0
        self.regs = [0]*16
        self.WIDTH = 64
        self.HEIGHT = 32
        self.delay = 0
        self.sound = 0
        self.key_states = [False]*16
        self.FONT_LOCATION = 0x20

        self.got_key = False
        self.waiting_for_key = False
        self.selected_key = 0

        self.load_fonts()

        self.display_clear()
        self.parse_file(filename)
        threading.Thread.__init__(self)

        self.data_lock = threading.Lock()
        self.emulate = False
        self.freq = processor_frequency

    def run(self):
        while True:
            if self.emulate:
                logging.debug("tick")
                self._tick()
                time.sleep(1.0/self.freq)        
            else:
                time.sleep(0.1)
    
    def toggle_live_emu(self):
        self.emulate = not self.emulate
    
    
    def get_display(self):
        disp = None
        with self.data_lock:
            disp = copy.deepcopy(self.display)
        return disp

    def get_regs(self):
        regs = None
        with self.data_lock:
            regs = {"regs": copy.deepcopy(self.regs),
                    "I": self.I,
                    "stack": copy.deepcopy(self.stack),
                    "PC": self.PC
            }
        return regs

    def parse_file(self, filename):
        with open(filename, 'rb') as f:
            raw_bytes = f.read()
        logging.debug("read raw bytes")
        logging.debug(raw_bytes)

        for i, byte in enumerate(raw_bytes):
            self.mem[i + 512] = byte


    def load_fonts(self):
        location = self.FONT_LOCATION
        for number in NUMBER_FONT:
            for byte in number:
                self.mem[location] = byte
                location += 1

    def fetch(self):
        val = self.mem[self.PC + 1] | (self.mem[self.PC] << 8)
        logging.debug(f"got opcode {hex(val)}")
        self.PC += 2
        return val

    def display_clear(self):
        self.display = [[0]*self.HEIGHT for _ in range(self.WIDTH)]

    def upper_nibble(self, opcode):
        return (opcode & COMMAND_MASK) >> 12

    def handle_call(self, opcode):
        if opcode == 0x00E0:
            self.display_clear()
        elif opcode == 0x00EE:
            address = self.stack.pop()
            self.PC = address
        else:
            raise Exception(f"Opcode {opcode} not yet implemented")

    def goto(self, opcode):
        address = (opcode & 0xFFF)
        self.PC = address

    def subroutine(self, opcode):
        address = opcode & 0xFFF
        self.stack.append(self.PC)
        self.PC = address

    def ifequal(self, opcode):
        reg = (opcode & 0x0F00) >> 8
        val = (opcode & 0x00FF)
        if self.regs[reg] == val:
            self.PC += 2

    def ifnequal(self, opcode):
        reg = (opcode & 0x0F00) >> 8
        val = (opcode & 0x00FF)
        if self.regs[reg] != val:
            self.PC += 2

    def regequal(self, opcode):
        Vx = (opcode & 0x0F00) >> 8
        Vy = (opcode & 0x00F0) >> 4
        if self.regs[Vx] == self.regs[Vy]:
            self.PC += 2

    def regnequal(self, opcode):
        Vx = (opcode & 0x0F00) >> 8
        Vy = (opcode & 0x00F0) >> 4
        if self.regs[Vx] != self.regs[Vy]:
            self.PC += 2

    def constsetreg(self, opcode):
        reg = (opcode & 0x0F00) >> 8
        val = (opcode & 0x00FF)
        self.regs[reg] = val

    def constadd(self, opcode):
        reg = (opcode & 0x0F00) >> 8
        val = (opcode & 0x00FF)
        self.regs[reg] += val

    def regmath(self, opcode):
        operator = opcode & 0x000F
        Vx = (opcode & 0x0F00) >> 8
        Vy = (opcode & 0x00F0) >> 4
        if operator == 0:
            self.regs[Vx] = self.regs[Vy]
        elif operator == 1:
            self.regs[Vx] |= self.regs[Vy]
        elif operator == 2:
            self.regs[Vx] &= self.regs[Vy]
        elif operator == 3:
            self.regs[Vx] ^= self.regs[Vy]
        elif operator == 4:
            self.regs[Vx] += self.regs[Vy]
            if self.regs[Vx] > 255:
                self.regs[0xF] = 1
            else:
                self.regs[0xF] = 0
        elif operator == 5:
            self.regs[Vx] -= self.regs[Vy]

            if self.regs[Vx] > self.regs[Vy]:
                self.regs[0xF] = 1
            else:
                self.regs[0xF] = 0
        elif operator == 6:
            self.regs[0xF] = Vx & 0x1
            self.regs[Vx] >>= 1
        elif operator == 7:
            self.regs[Vx] = self.regs[Vy] - self.regs[Vx]

            if self.regs[Vx] > self.regs[Vy]:
                self.regs[0xF] = 1
            else:
                self.regs[0xF] = 0
        elif operator == 0xE:
            # TODO(HEIDT) this is largely dependent on CHIP8 implementation!
            self.regs[0xF] = Vx & 0x80
            self.regs[Vx] <<= 1

    def setI(self, opcode):
        val = opcode & 0xFFF
        self.I = val

    def jmpoff(self, opcode):
        val = opcode & 0xFFF
        self.PC = self.regs[0] + val

    def rand(self, opcode):
        mask = opcode & 0xFF
        Vx = (opcode & 0x0F00) >> 8
        self.regs[Vx] = random.randint(0, 255) & mask

    def draw(self, opcode):
        Vx = (opcode & 0x0F00) >> 8
        Vy = (opcode & 0x00F0) >> 4
        x = self.regs[Vx] % self.WIDTH
        y = self.regs[Vy] % self.HEIGHT
        self.regs[0xF] = 0
        N = opcode & 0x000F
        for y_change in range(N):
            sprite_data = self.mem[self.I + y_change]
            x = self.regs[Vx] % self.WIDTH
            for i in range(8):
                bit = (sprite_data >> (7 - i)) & 0x1
                if self.display[x][y] == 1 and bit == 1:
                    self.display[x][y] = 0
                    self.regs[0xF] = 0
                elif self.display[x][y] == 0 and bit == 1:
                    self.display[x][y] = 1
                if x >= self.WIDTH - 1:
                    break
                x += 1
            y += 1

    def clipregs(self):
        for i, reg in enumerate(self.regs):
            self.regs[i] = reg & 0xFFFF

    def keys(self, opcode):
        lower = opcode & 0xFF
        Vx = (opcode & 0x0F00) >> 8
        Vxreg = self.regs[Vx]
        if lower == 0x9E:
            if self.key_states[Vxreg]:
                self.PC += 2
        elif lower == 0xA1:
            if not self.key_states[Vxreg]:
                self.PC += 2
        else:
            raise Exception(f"opcode {opcode} not implemented")

    def system(self, opcode):
        lower = opcode & 0xFF
        Vx = (opcode & 0x0F00) >> 8
        Vxreg = self.regs[Vx]
        if lower == 0x07:
            self.regs[Vx] = self.delay_timer
        elif lower == 0x0A:
            if self.waiting_for_key:
                if self.got_key:
                    self.waiting_for_key = False
                    self.regs[Vx] = self.selected_key
                    self.PC += 2
            else:
                self.waiting_for_key = True
            self.PC -= 2
        elif lower == 0x15:
            self.delay_timer = Vxreg
        elif lower == 0x18:
            self.sound_timer = Vxreg
        elif lower == 0x1E:
            self.I += Vxreg
        elif lower == 0x29:
            self.I = self.FONT_LOCATION + 5*Vxreg
        elif lower == 0x33:
            num = Vx
            self.mem[self.I] = (num % 10)
            self.mem[self.I + 1] = (num % 100) - self.mem[self.I]
            self.mem[self.I + 2] = num - self.mem[self.I] - self.mem[self.I + 1]
        elif lower == 0x55:
            for i, reg in enumerate(self.regs):
                self.mem[self.I + i] = reg
        elif lower == 0x65:
            for i, reg in enumerate(self.regs):
                self.regs[i] = self.mem[self.I + i]
        else:
            raise Exception(f"opcode {opcode} not implemented!")
        

    def decode(self, opcode):
        nibble = self.upper_nibble(opcode)
        if nibble == 0x0:
            logging.debug("op call")
            self.handle_call(opcode)
        elif nibble == 0x1:
            logging.debug("op goto")
            self.goto(opcode)
        elif nibble == 0x2:
            logging.debug("op subroutine")
            self.subroutine(opcode)
        elif nibble == 0x3:
            logging.debug("op ifequal")
            self.ifequal(opcode)
        elif nibble == 0x4:
            logging.debug("op ifnequal")
            self.ifnequal(opcode)
        elif nibble == 0x5:
            logging.debug("op regequal")
            self.regequal(opcode)
        elif nibble == 0x6:
            logging.debug("op const set reg")
            self.constsetreg(opcode)
        elif nibble == 0x7:
            logging.debug("op const add")
            self.constadd(opcode)
        elif nibble == 0x8:
            logging.debug("op regmath")
            self.regmath(opcode)
        elif nibble == 0x9:
            logging.debug("op regnequal")
            self.regnequal(opcode)
        elif nibble == 0xA:
            logging.debug("op setI")
            self.setI(opcode)
        elif nibble == 0xB:
            logging.debug("op jmp")
            self.jmpoff(opcode)
        elif nibble == 0xC:
            logging.debug("op rand")
            self.rand(opcode)
        elif nibble == 0xD:
            logging.debug("op draw")
            self.draw(opcode)
        elif nibble == 0xE:
            logging.debug("keys")
            self.keys(opcode)
        elif nibble == 0xF:
            logging.debug("system")
            self.system(opcode)
        else:
            raise Exception(f"opcode {opcode} not implemented!")

    def _tick(self):
        with self.data_lock:
            value = self.fetch()
            self.decode(value)
            self.clipregs()

    def set_key(self, key: int, value: bool):
        """Call this function when a key is pressed

        Args:
            key (int): key index from 0x0-0xF
            value (bool): key value True if pressed, False if released
        """
        with self.data_lock:
            self.key_states[key] = value
            if self.waiting_for_key:
                self.got_key = True
                self.selected_key = key

    def tick(self):
        if not self.emulate:
            self._tick()