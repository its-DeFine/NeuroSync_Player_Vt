import gi, sys, time, logging
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject
Gst.init(None)

logging.basicConfig(level=logging.INFO)
rtmp_url = "rtmp://localhost/live/audiostream"

def stream_wav_to_rtmp(wav_path: str,
                       rtmp_url: str,
                       blocking: bool = True) -> None:
    """
    Streams a local WAV file to an RTMP server (e.g. OBS).  Non-blocking
    mode returns immediately after starting the pipeline.
    """
    pipeline_desc = (
        # ---------- Audio ----------
        f"filesrc location={wav_path} ! wavparse ! audioconvert ! "
        f"voaacenc bitrate=128000 ! queue ! mux. "
        # ---------- Dummy Video ----------
        # "videotestsrc is-live=true pattern=black ! "
        # "video/x-raw,width=640,height=360,framerate=30/1 ! "
        # "x264enc tune=zerolatency bitrate=1500 speed-preset=ultrafast key-int-max=30 ! "
        # "queue ! mux. "
        # ---------- Mux & Push ----------
        "flvmux name=mux streamable=true ! "
        f"rtmpsink location=\"{rtmp_url}\""
    )
    logging.info("Launching GStreamer pipeline:\n%s", pipeline_desc)
    pipeline = Gst.parse_launch(pipeline_desc)
    pipeline.set_state(Gst.State.PLAYING)

    if not blocking:
        return

    # —––– Wait until EOS or ERROR ––––
    bus = pipeline.get_bus()
    while True:
        msg = bus.timed_pop_filtered(
            Gst.SECOND,
            Gst.MessageType.EOS | Gst.MessageType.ERROR
        )
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, dbg = msg.parse_error()
                logging.error("GStreamer error: %s", err)
            break
        time.sleep(0.1)

    pipeline.set_state(Gst.State.NULL)

