# Third-party notices

The application source in this repository is MIT-licensed (see `LICENSE`). The bundled pretrained model files are third-party artifacts with separate terms.

## YOLOv8n ONNX (object detection)

- File: `models/yolov8n.onnx`
- Source: Hugging Face model repository `Kalray/yolov8`, file `yolov8n.onnx` — https://huggingface.co/Kalray/yolov8/blob/main/yolov8n.onnx
- Direct download used by `scripts/download_models.py`: https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx
- Model family: Ultralytics YOLOv8 nano, COCO classes.
- License: Ultralytics YOLOv8 is distributed under AGPL-3.0. Ultralytics also offers commercial licenses. Review https://github.com/ultralytics/ultralytics/blob/main/LICENSE before commercial deployment.
- SHA-256 expected by the downloader: `65158dad735be799c2466fa15e260c09558080bd530b42a8d0c3d1b419afd8b5`
- Usage here: OpenCV DNN CPU inference; no PyTorch required.

## TwinLiteNet ONNX (drivable area + lane segmentation)

- File: `models/twinlitenet_da.onnx` (original filename `best.onnx`)
- Source: `harrylal/TwinLiteNet-onnx-opencv-dnn` — https://github.com/harrylal/TwinLiteNet-onnx-opencv-dnn
- Direct download: https://raw.githubusercontent.com/harrylal/TwinLiteNet-onnx-opencv-dnn/main/models/best.onnx
- Original model: Che Quang Huy, TwinLiteNet — https://github.com/chequanghuy/TwinLiteNet
- License: MIT. Wrapper repository MIT; original TwinLiteNet MIT, Copyright (c) 2023 Chế Quang Huy.
- SHA-256 expected by the downloader: `f505b56bd7c9e4e38b2928373aa4daa191a9a398e07e1fb340024b9ce84d4285`
- Paper: TwinLiteNet: An Efficient and Lightweight Model for Driveable Area and Lane Segmentation in Self-Driving Cars, arXiv:2307.10705. https://arxiv.org/html/2307.10705v5

MIT license text for TwinLiteNet / wrapper:

> Copyright (c) 2023 Chế Quang Huy
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Sample image

- File: `assets/sample_road.jpg`
- Source: Ultralytics repository sample `ultralytics/assets/bus.jpg` — https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/assets/bus.jpg
- Used only as a local perception smoke-test image. It is not claimed to be a calibrated driving dataset sample.

## Frontend/backend libraries

FastAPI, Uvicorn, OpenCV, NumPy, SciPy, aiortc, qrcode, psutil, React, Vite, Three.js, React Three Fiber, Drei, Recharts, Tailwind CSS and their transitive dependencies retain their respective licenses. Installed package metadata is authoritative.
