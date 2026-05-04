import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision import models

try:
    from albumentations import Compose, Normalize, Resize
    from albumentations.pytorch import ToTensorV2
except ImportError:
    raise ImportError('Installe albumentations pour lancer ce script : pip install albumentations')


def load_config(checkpoint_path: Path):
    config_path = checkpoint_path.parent / 'model_config.json'
    if config_path.exists():
        return json.loads(config_path.read_text())
    return None


def build_model(model_name: str, num_classes: int = 4):
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
    image = np.array(Image.open(image_path).convert('RGB'))
    transform = Compose([
        Resize(image_size, image_size),
        Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])
    return transform(image=image)['image'].unsqueeze(0)


def load_checkpoint(checkpoint_path: Path, model_name: str, device: torch.device):
    config = load_config(checkpoint_path)
    num_classes = config.get('num_classes', 4) if config else 4
    class_names = config.get('classes') if config else None
    model = build_model(model_name, num_classes=num_classes)
    state = torch.load(checkpoint_path, map_location=device)
    if 'model_state_dict' in state:
        model.load_state_dict(state['model_state_dict'])
    else:
        model.load_state_dict(state)
    model.to(device)
    model.eval()
    return model, class_names


def predict(checkpoint: Path, image: Path, model_name: str, image_size: int, device: str):
    device = torch.device(device if torch.cuda.is_available() and device == 'cuda' else 'cpu')
    model, class_names = load_checkpoint(checkpoint, model_name, device)
    input_tensor = preprocess(image, image_size).to(device)
    with torch.no_grad():
        output = model(input_tensor)
        pred_idx = output.argmax(dim=1).item()
    if class_names is None:
        class_names = [f'class_{i}' for i in range(output.shape[1])]
    return class_names[pred_idx]


def parse_args():
    parser = argparse.ArgumentParser(description='Prédire le volume et la confiance avec un modèle entraîné')
    parser.add_argument('--checkpoint', type=Path, required=True, help='Chemin du checkpoint .pth')
    parser.add_argument('--image', type=Path, required=True, help='Image à prédire')
    parser.add_argument('--model-name', type=str, default='resnet18', choices=['resnet18', 'resnet50', 'efficientnet_b0'])
    parser.add_argument('--image-size', type=int, default=224)
    parser.add_argument('--device', type=str, default='cpu', choices=['cpu', 'cuda'])
    return parser.parse_args()


def main():
    args = parse_args()
    label = predict(args.checkpoint, args.image, args.model_name, args.image_size, args.device)
    print(f"Classe prédite : {label}")


if __name__ == '__main__':
    main()
