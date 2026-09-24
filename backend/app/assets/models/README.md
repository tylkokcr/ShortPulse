# Bundled models

## face_detection_yunet.onnx

YuNet face detector, from [opencv_zoo][zoo] (`face_detection_yunet_2023mar.onnx`),
MIT licensed. 233KB.

Vendored rather than downloaded at first use, for the same reason the
outro font is: a self-hosted install should work offline, and the first
render should not also be the first download. It is small enough that
this costs nothing — the Whisper and Piper models are downloaded because
they are hundreds of megabytes, and this is not.

Used by `app/services/reframe.py` to follow the speaker when a landscape
recording is cut into vertical clips. Requires `opencv-python-headless`
(see `requirements-vision.txt`); absent, clips are centre-cropped.

    sha256  8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4

[zoo]: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
