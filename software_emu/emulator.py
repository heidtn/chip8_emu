import argparse
import time
import logging
from enum import Enum
import random
import PySimpleGUI as sg
from PIL import Image, ImageTk



class Chip8State(Enum):
    FETCH = 1
    DECODE = 2
    EXECUTE = 3



NUMBER_FONT = [
    [0xF0, 0x90, 0x90, 0x90, 0xF0], # 0
    [0x20, 0x60, 0x20, 0x20, 0x70], # 1
    [0xF0, 0x10, 0xF0, 0x80, 0xF0], # 2
    [0xF0, 0x10, 0xF0, 0x10, 0xF0], # 3
    [0x90, 0x90, 0xF0, 0x10, 0x10], # 4
    [0xF0, 0x80, 0xF0, 0x10, 0xF0], # 5
    [0xF0, 0x80, 0xF0, 0x90, 0xF0], # 6
    [0xF0, 0x10, 0x20, 0x40, 0x40], # 7
    [0xF0, 0x90, 0xF0, 0x90, 0xF0], # 8
    [0xF0, 0x90, 0xF0, 0x10, 0xF0], # 9
    [0xF0, 0x90, 0xF0, 0x90, 0x90], # A
    [0xE0, 0x90, 0xE0, 0x90, 0xE0], # B
    [0xF0, 0x80, 0x80, 0x80, 0xF0], # C
    [0xE0, 0x90, 0x90, 0x90, 0xE0], # D
    [0xF0, 0x80, 0xF0, 0x80, 0xF0], # E
    [0xF0, 0x80, 0xF0, 0x80, 0x80], # F
]

COMMAND_MASK = 0xF000

logging.basicConfig(level=logging.DEBUG)


class Chip8EMU:
    def __init__(self, filename, processor_frequency=1e6):
        self.mem = [0]*4096
        self.stack = []
        self.delay_timer = 0
        self.PC = 512
        self.I = 0
        self.regs = [0]*16
        self.WIDTH = 64
        self.HEIGHT = 32

        self.display_clear()
        self.parse_file(filename)


    def setup_GUI(self):
        logging.info("Setting up GUI")
        self.display_image = Image.new("RGB", (self.WIDTH, self.HEIGHT), (255, 255, 255))

        layout = [
            [sg.Image(key="-DISPLAY-")],
            [sg.InputText('0', key=f"V{i}", size=(3, None)) for i in range(0xF)],
            [sg.Text("I"), sg.InputText('0', key=f"I", size=(3, None))],
            [sg.Button("Tick")]
        ]
        self.window = sg.Window(title="CHIP8 EMU", layout=layout, margins=(100, 50))

    def update_inputs(self):
        for i in range(0xF):
            self.window[f"V{i}"].update(self.regs[i])
        self.window["I"].update(self.I)

    def run(self):
        self.setup_GUI()
        logging.info("running GUI")
        while True:
            event, values = self.window.read()

            print(event, values)
            if event == "Tick":
                self.tick()
            if event == sg.WIN_CLOSED:
                break

            self.update_inputs()
            self.update_image()

            resized = self.display_image.resize((self.WIDTH*5, self.HEIGHT*5))
            image = ImageTk.PhotoImage(resized)
            self.window["-DISPLAY-"].update(data=image)

    def update_image(self):
        pixels = self.display_image.load()
        print(self.display_image.size)
        for x in range(self.WIDTH):
            for y in range(self.HEIGHT):
                pixels[x, self.HEIGHT - y - 1] = (0, 255*self.display[x][y], 0)

    def parse_file(self, filename):
        with open(filename, 'rb') as f:
            raw_bytes = f.read()
        logging.debug("read raw bytes")
        logging.debug(raw_bytes)

        for i, byte in enumerate(raw_bytes):
            self.mem[i + 512] = byte

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
            sprite_data = self.mem[self.I + N]
            x = self.regs[Vx] % self.WIDTH
            for i in range(8):
                bit = (sprite_data & (1 << i)) >> i
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
            raise Exception("Not implemented")
        elif nibble == 0xF:
            self.system(opcode)

    def tick(self):
        value = self.fetch()
        self.decode(value)

        self.clipregs()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")

    args = parser.parse_args()

    emu = Chip8EMU(args.filename)
    emu.run()


if __name__ == "__main__":
    main()