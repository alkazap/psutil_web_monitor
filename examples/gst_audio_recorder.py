import argparse
import datetime
import os
import sys

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
gi.require_version('GLib', '2.0')
gi.require_version('GObject', '2.0')
from gi.repository import GLib, GObject, Gst, GstPbutils
import threading


class AudioRecorder():
    def __init__(self, loop: GLib.MainLoop, format: str, location: str, duration: int):
        self.loop = loop
        self.format = format
        self.location = location
        self.build_pipeline()
        if duration > 0:
            self.duration = duration
            # Callback will be called at regular intervals
            GLib.timeout_add_seconds(interval=1, function=self.timeout_function)

    def build_pipeline(self):
        self.pipeline = Gst.Pipeline.new('pipeline')
        if not self.pipeline:
            print("ERROR: Could not create Gst.Pipeline", file=sys.stderr)
            sys.exit(-1)

        self.alsasrc = Gst.ElementFactory.make(
            factoryname='alsasrc', name='alsasrc')
        self.decodebin = Gst.ElementFactory.make(
            factoryname='decodebin', name='decodebin')
        self.audioconvert = Gst.ElementFactory.make(
            factoryname='audioconvert', name='audioconvert')
        self.audioresample = Gst.ElementFactory.make(
            factoryname='audioresample', name='audioresample')
        self.tee = Gst.ElementFactory.make(factoryname='tee', name='tee')
        self.queue1 = Gst.ElementFactory.make(
            factoryname='queue', name='queue1')
        self.queue2 = Gst.ElementFactory.make(
            factoryname='queue', name='queue2')
        self.filesink = Gst.ElementFactory.make(
            factoryname='filesink', name='filesink')
        output_file = "%s/%s.%s" % (self.location,
                                     datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S"), self.format)
        self.filesink.set_property('location', output_file)
        self.fakesink = Gst.ElementFactory.make(
            factoryname='fakesink', name='fakesink')

        self.add_elements([self.alsasrc, self.decodebin])
        self.link_elements([self.alsasrc, self.decodebin])

        elements = [self.audioconvert, self.audioresample, self.tee, self.queue1]
        if (self.format == 'wav'):
            self.wavenc = Gst.ElementFactory.make(
                factoryname='wavenc', name='wavenc')
            elements.append(self.wavenc)
        elif (self.format == 'ogg'):
            self.vorbisenc = Gst.ElementFactory.make(
                factoryname='vorbisenc', name='vorbisenc')
            self.oggmux = Gst.ElementFactory.make(
                factoryname='oggmux', name='oggmux')
            elements.append(self.vorbisenc)
            elements.append(self.oggmux)
        elif (self.format == 'mp3'):
            self.lame = Gst.ElementFactory.make(
                factoryname='lame', name='lame') 
            elements.append(self.lame)
        elif (self.format == 'flac'):
            self.flacenc = Gst.ElementFactory.make(
                factoryname='flacenc', name='flacenc')
            elements.append(self.flacenc)

        elements.append(self.filesink)
        self.add_elements(elements)
        self.link_elements(elements)

        self.add_elements([self.queue2, self.fakesink])
        self.link_elements([self.tee, self.queue2, self.fakesink])

        self.connect_signals()

        if self.pipeline.set_state(Gst.State.READY) == Gst.StateChangeReturn.FAILURE:
            print("ERROR: Unable to set the Gst.Pipeline state to READY",
                  file=sys.stderr)
            self.finish()
            sys.exit(-1)

    def add_elements(self, elements: list):
        for element in elements:
            if element:
                self.pipeline.add(element)
                print("Added '%s'" % element.get_name())
            else:
                print("ERROR: Could not create '%s'" %
                      element.get_name())
                self.finish()
                sys.exit(-1)

    def link_elements(self, elements: list):
        elements_iter = iter(elements)
        src_element = next(elements_iter)
        for dst_element in elements_iter:
            if not src_element.link(dst_element):
                print("ERROR: Could not link '%s' to '%s'" %
                    (src_element.get_name(), dst_element.get_name()), file=sys.stderr)
                self.finish()
                sys.exit(-1)
            else:
                print("Linked %s to %s" % (src_element.get_name(), dst_element.get_name()))
            src_element = dst_element

    def connect_signals(self):
        # Connect decodebin 'pad-added' signal
        self.decodebin.connect('pad-added', self.pad_added_handler)
        # Retrieve bus to receive Gst.Message from the elemetins in the pipeline
        self.bus = self.pipeline.get_bus()
        # Add a bus signal watch to the default main context with the default priority
        # the bus will emit the 'message' signal for each message posted on the bus
        self.bus.add_signal_watch()
        # If the default GLib mainloop integration is used, it is possible
        # to connect to the 'message' signal on the bus in form of 'message::<type>'
        self.bus.connect("message", self.message_handler)

    def pad_added_handler(self, element, pad):
        if element is self.decodebin:
            # Link decodebin's src pad to audioconvert's sink
            audioconvert_pad = self.audioconvert.get_static_pad('sink')
            if not audioconvert_pad.is_linked():
                if pad.link(audioconvert_pad) is not Gst.PadLinkReturn.OK:
                    print(
                        "ERROR: 'decoder' and 'audioconvert' could not be linked", file=sys.stderr)
                    self.finish()
                    sys.exit(-1)
                else:
                    print("Linked 'decodebin' to 'audioconvert'")
            else:
                print(
                    "ERROR: audioconvert's sink pad is already linked")

            Gst.debug_bin_to_dot_file_with_ts(
                self.pipeline, Gst.DebugGraphDetails.ALL, 'pipeline')
            

    def message_handler(self, bus, message):
        if message.type == Gst.MessageType.EOS:
            print("End-of-stream reached")
            self.finish()
        elif message.type == Gst.MessageType.ERROR:
            error, debug_info = message.parse_error()
            print("Error received from Gst.Element '%s': %s" %
                  (message.src.get_name(), error.message), file=sys.stderr)
            if debug_info:
                print("Debug info: %s" % debug_info, file=sys.stderr)
            self.finish()
        return True

    def timeout_function(self):
        # Stream position in nanoseconds - between 0 and the total stream duration
        # Gst.SECOND = 1000000000
        _, position = self.pipeline.query_position(Gst.Format.TIME)
        print("Position: %d" % int(position / Gst.SECOND))
        if position > self.duration * Gst.SECOND:
            print("Recording stopped after %d seconds" % self.duration)
            self.finish()
            return False
        return True

    def start(self):
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            print("ERROR: Unable to set the Gst.Pipeline state to PLAYING",
                  file=sys.stderr)
            self.finish()
            sys.exit(-1)

    def finish(self):
        print("Finish")
        # Free resources
        if self.loop.is_running():
            print("Quit loop")
            self.loop.quit()
        self.pipeline.set_state(Gst.State.NULL)
        # Wait for state change
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE)


def main():
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='GStreamer record sound example')
    parser.add_argument('-l', '--location', dest='location', type=str,
                        default='tmp', help='Location of the file to write')
    parser.add_argument('-d', '--duration', dest='duration',
                        type=int, default=-1, help='Recording duration')
    parser.add_argument('-f', '--format', dest='format',
                        type=str, default='raw', choices=['wav', 'ogg', 'mp3', 'flac', 'raw'], help='Audio file format')
    args = parser.parse_args()
    if not os.path.exists(args.location):
        os.mkdir(args.location)
    elif not os.path.isdir(args.location):
        print("ERROR: Output location %s already exists as a file" %
              args.location, file=sys.stderr)
        sys.exit(-1)

    # Initialize GStreamer
    Gst.init(None)
    GLib.threads_init()
    loop = GLib.MainLoop.new(None, False)
    recorder = AudioRecorder(loop=loop, format=args.format, location=args.location, duration=args.duration)
    recorder.start()
    thread = threading.Thread(target=loop.run(), args=(), daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        print("Got SGINT")
        recorder.finish()
        thread.join()

if __name__ == "__main__":
    main()
