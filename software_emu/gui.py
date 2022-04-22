import argparse
import logging
import PySimpleGUI as sg
from PIL import Image, ImageTk
import emulator

logging.basicConfig(level=logging.DEBUG)


class Chip8GUI:
    def __init__(self, filename, processor_frequency=1e6):
        self.emu = emulator.Chip8EMU(filename, processor_frequency)
        self.emu.start()
        self.SCREEN_SCALE = 10
        self.running = False

    def setup_GUI(self):
        logging.info("Setting up GUI")
        self.display_image = Image.new(
            "RGB", (self.emu.WIDTH, self.emu.HEIGHT), (255, 255, 255))

        layout = [
            [sg.Image(key="-DISPLAY-")],
            [sg.InputText('0', key=f"V{i}", size=(3, None))
             for i in range(0xF)],
            [sg.Text("I"), sg.InputText('0', key=f"I", size=(3, None))],
            [sg.Button("Tick"), sg.Button("Run")]
        ]
        self.window = sg.Window(title="CHIP8 EMU", layout=layout, 
                                margins=(100, 50), element_justification='c',
                                return_keyboard_events=True)

    def update_inputs(self):
        regs = self.emu.get_regs()
        for i in range(0xF):
            self.window[f"V{i}"].update(regs["regs"][i])
        self.window["I"].update(regs["I"])

    def run(self):
        self.setup_GUI()
        logging.info("running GUI")
        while True:
            event, values = self.window.read(timeout=100)

            if event == "Tick":
                self.emu.tick()
            if event == "Run":
                self.emu.toggle_live_emu()
            if event == sg.WIN_CLOSED:
                break

            self.update_inputs()
            self.update_image()

            resized = self.display_image.resize(
                (self.emu.WIDTH*self.SCREEN_SCALE, self.SCREEN_SCALE*self.emu.HEIGHT))
            image = ImageTk.PhotoImage(resized)
            self.window["-DISPLAY-"].update(data=image)

    def update_image(self):
        pixels = self.display_image.load()
        display = self.emu.get_display()
        for x in range(self.emu.WIDTH):
            for y in range(self.emu.HEIGHT):
                pixels[x, y] = (0, 255*display[x][y], 0)



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")

    args = parser.parse_args()

    emu = Chip8GUI(args.filename)
    emu.run()


if __name__ == "__main__":
    main()
