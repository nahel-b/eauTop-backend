import argparse
import json
import os
from pathlib import Path

os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['TORCH_HOME'] = os.environ.get('TORCH_HOME', str(Path.home() / '.cache' / 'torch'))

import numpy as np
from PIL import Image

try:
    import onnxruntime as ort
    ONNX_RUNTIME_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_RUNTIME_AVAILABLE = False


def import_torch():
    try:
        import torch
        from torchvision import models
    except ImportError as exc:
        raise ImportError('Installe torch et torchvision pour utiliser le mode checkpoint PyTorch') from exc

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.set_grad_enabled(False)
    return torch, models

MODEL_CACHE = {}
SESSION_CACHE = {}


def load_config(path: Path):
    config_path = path.parent / 'model_config.json'
    if config_path.exists():
        return json.loads(config_path.read_text())
    return None


def build_model(model_name: str, num_classes: int = 4):
    torch, models = import_torch()

    if model_name == 'resnet18':
        model = models.resnet18(pretrained=False)
        in_features = model.fc.in_features
        model.fc = torch.nn.Sequential(
            torch.nn.Linear(in_features, 256),
            torch.nn.ReLU(inplace=True),
            torch.nn.Dropout(p=0.2),
            torch.nn.Linear(256, num_classes),
        )
    elif model_name == 'resnet50':
        model = models.resnet50(pretrained=False)
        in_features = model.fc.in_features
        model.fc = torch.nn.Sequential(
            torch.nn.Linear(in_features, 256),
            torch.nn.ReLU(inplace=True),
            torch.nn.Dropout(p=0.2),
            torch.nn.Linear(256, num_classes),
        )
    elif model_name == 'efficientnet_b0':
        model = models.efficientnet_b0(pretrained=False)
        in_features = model.classifier[1].in_features
        model.classifier = torch.nn.Sequential(
            torch.nn.Dropout(p=0.2, inplace=True),
            torch.nn.Linear(in_features, 256),
            torch.nn.ReLU(inplace=True),
            torch.nn.Dropout(p=0.2, inplace=True),
            torch.nn.Linear(in_features, num_classes),
        )
    else:
        raise ValueError('model-name invalide')
    return model


def preprocess(image_path: Path, image_size: int):
    image = Image.open(image_path).convert('RGB')
    image = image.resize((image_size, image_size), Image.BILINEAR)
    image = np.array(image).astype(np.float32) / 255.0
    image = (image - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    image = image.transpose(2, 0, 1)
    return np.expand_dims(image, axis=0)


def load_checkpoint(checkpoint_path: Path, model_name: str, device):
    torch, _ = import_torch()
    config = load_config(checkpoint_path)
    num_classes = config.get('num_classes', 4) if config else 4
    class_names = config.get('classes') if config else None

    model = build_model(model_name, num_classes=num_classes)
    state = torch.load(checkpoint_path, map_location=device)
    if isinstance(state, dict) and 'model_state_dict' in state:
        model.load_state_dict(state['model_state_dict'])
    else:
        model.load_state_dict(state)

    model.to(device)
    model.eval()
    return model, class_names


def get_cached_model(checkpoint_path: Path, model_name: str, device):
    cache_key = (str(checkpoint_path), model_name, str(device))
    if cache_key not in MODEL_CACHE:
        MODEL_CACHE[cache_key] = load_checkpoint(checkpoint_path, model_name, device)
    return MODEL_CACHE[cache_key]


def load_onnx_session(onnx_path: Path):
    if not ONNX_RUNTIME_AVAILABLE:
        raise ImportError('onnxruntime n\'est pas installé. Installe le avec pip install onnxruntime')

    if onnx_path not in SESSION_CACHE:
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(str(onnx_path), sess_options=sess_options, providers=['CPUExecutionProvider'])
        SESSION_CACHE[onnx_path] = session
    return SESSION_CACHE[onnx_path]


def get_class_names(path: Path, num_classes: int):
    config = load_config(path)
    if config and isinstance(config.get('classes'), list):
        return config['classes']
    return [f'class_{i}' for i in range(num_classes)]


def softmax(logits: np.ndarray):
    exp = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
    return exp / np.sum(exp, axis=-1, keepdims=True)


def predict_torch(checkpoint: Path, image: Path, model_name: str, image_size: int, device: str):
    torch, _ = import_torch()
    device = torch.device(device if torch.cuda.is_available() and device == 'cuda' else 'cpu')
    model, class_names = get_cached_model(checkpoint, model_name, device)
    input_tensor = torch.tensor(preprocess(image, image_size), dtype=torch.float32, device=device)
    with torch.inference_mode():
        output = model(input_tensor)
        probs = torch.nn.functional.softmax(output, dim=1)
        pred_idx = int(probs.argmax(dim=1).item())
        confidence = float(probs[0, pred_idx].item())
    if class_names is None:
        class_names = [f'class_{i}' for i in range(output.shape[1])]
    return class_names[pred_idx], confidence


def predict_onnx(onnx_path: Path, image: Path, image_size: int):
    session = load_onnx_session(onnx_path)
    input_tensor = preprocess(image, image_size).astype(np.float32)
    outputs = session.run(None, {'input': input_tensor})
    output = outputs[0]
    probs = softmax(output)
    pred_idx = int(np.argmax(probs, axis=1)[0])
    confidence = float(probs[0, pred_idx])
    class_names = get_class_names(onnx_path, output.shape[1])
    return class_names[pred_idx], confidence


def parse_args():
    parser = argparse.ArgumentParser(description='Prédire le volume et la confiance avec un modèle entraîné')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--checkpoint', type=Path, help='Chemin du checkpoint .pth')
    group.add_argument('--onnx-model', type=Path, help='Chemin du modèle ONNX à utiliser pour l\'inférence')
    parser.add_argument('--image', type=Path, required=True, help='Image à prédire')
    parser.add_argument('--model-name', type=str, default='resnet18', choices=['resnet18', 'resnet50', 'efficientnet_b0'])
    parser.add_argument('--image-size', type=int, default=224)
    parser.add_argument('--device', type=str, default='cpu', choices=['cpu', 'cuda'])
    return parser.parse_args()


def main():
    args = parse_args()
    if args.onnx_model:
        predicted_class, confidence = predict_onnx(args.onnx_model, args.image, args.image_size)
    else:
        predicted_class, confidence = predict_torch(args.checkpoint, args.image, args.model_name, args.image_size, args.device)
    result = {
        'predicted_class': predicted_class,
        'confidence': confidence,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
