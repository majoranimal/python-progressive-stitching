import ffmpeg, config, signal, logging
from PIL import Image
from io import BytesIO

logging.basicConfig(level=logging.DEBUG)


### Imports a specific frame of the video and converts it to an image with pillow
def get_frame_as_image(frame_num: int) -> tuple:
    logging.debug('gf start')
    try:
        raw = ffmpeg.input(config.inputfile) \
            .filter('select', f'gte(n, {frame_num})') \
            .output(f"pipe:", format='image2pipe', codec='targa', vframes=1, ) \
            .run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as e:
        logging.error(f"GF stdout: {e.stdout.decode('utf8')}")
        logging.error(f"GF stderr: {e.stderr.decode('utf8')}")
        raise e
    logging.debug('gf end')
    return Image.open(BytesIO(raw[0]))#.convert('RGBA')


# Write the provided frame to the stdin of the ffmpeg process that's creating the output file
def write_frame_to_output(frame: Image, ffmpeg_output: ffmpeg) -> None:
    logging.debug('wf start')
    output_frame = BytesIO()
    logging.debug('wf bytes')
    frame.save(output_frame, format='BMP')
    logging.debug('wf save')
    ffmpeg_output.stdin.write(output_frame.getbuffer().tobytes())
    logging.debug('wf end')

# Read the metadata of the file and write it to the 'video_metadata' variable
def get_video_metadata(filename: str) -> dict:
    video_streams = [s for s in ffmpeg.probe(filename, count_frames=None, loglevel="quiet")["streams"] if s["codec_type"] == "video"]
    assert len(video_streams) == 1
    return video_streams[0]


# Creates an asynchronous ffmpeg process that will produce an output video using PNG files provided with stdin
def create_output_processor(framerate: int, codec: str, filename: str, metadata: dict) -> ffmpeg:
    return ffmpeg.input('pipe:', framerate=framerate, format='bmp_pipe') \
        .output(f"{filename}", codec=f"{codec}") \
        .overwrite_output() \
        .run_async(pipe_stdin=True)


# Defines a signal handler function
def signal_handler(sig, frame):
    print('Interupt given: saving output.')
    global INTERRUPT
    INTERRUPT = True




# Create the metadata and initialise the output process
video_metadata = get_video_metadata(config.inputfile)
output = create_output_processor(config.framerate, config.outputcodec, config.outputfile, video_metadata)

# Setup the initial frame to prevent issues in the loop
compound_frame = get_frame_as_image(0)
write_frame_to_output(compound_frame, output)

# Creates a handler that will save the current output if an interupt is given
INTERRUPT = False
signal.signal(signal.SIGINT, signal_handler)

# For each frame of the input video take the compounded image of all previous frames and use it as the background for the next frame
for frame_num in range(0, int(video_metadata['nb_read_frames'])):
    logging.info(f"{frame_num}/{video_metadata['nb_read_frames']}")
    logging.debug('cgf start')
    current_frame = get_frame_as_image(frame_num) # Get the current frame of the video
    logging.debug('cgf end')

    logging.debug('ac start')
    compound_frame = Image.alpha_composite(compound_frame, current_frame) # Put the current frame on top of the progressively compounded frame
    logging.debug('ac end')

    logging.debug('cwf start')
    write_frame_to_output(compound_frame, output) # Write the new frame to the stdin of the output process
    logging.debug('cwf end')

    if INTERRUPT:
        break

# When the loop ends close the output process and wait until it's finished
output.stdin.close()
output.wait()