import argparse
import csv
import json
import math
import os
import random
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import albumentations as A
import numpy as np
import torch
from albumentations.pytorch import ToTensorV2
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}


# cd /Users/nahelbelmadani/Desktop/projets/eauTop-backend
# source .venv/bin/activate

# entrainer le modèle :
# python3 volume-estimation/train.py --data-dir volume-estimation/dataset_eauTop --model-name resnet50 --epochs 20 --batch-size 16 --output-dir volume-estimation/checkpoints --device cpu

# exporter le modèle entraîné en ONNX :
# python3 volume-estimation/export_onnx.py --checkpoint volume-estimation/checkpoints/resnet50_best.pth --model-name resnet50 --output volume-estimation/model_resnet50.onnx


try:
    from huggingface_hub import create_repo, upload_file
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def parse_volume_from_dir(name: str) -> float:
    name = name.replace('_', ' ').lower()
    ml_match = re.search(r"(\d+[.,]?\d*)\s*[mM][lL]", name)
    if ml_match:
        return float(ml_match.group(1).replace(',', '.'))

    litre_match = re.search(r"(\d+)(?:[.,](\d+))?\s*[lL]", name)
    if litre_match:
        litres = float(litre_match.group(1) + '.' + (litre_match.group(2) or '0'))
        return litres * 1000.0

    compact_match = re.search(r"(\d+)l(\d+)", name)
    if compact_match:
        litres = int(compact_match.group(1))
        decimals = int(compact_match.group(2))
        factor = 10 ** len(compact_match.group(2))
        return litres * 1000.0 + (decimals / factor) * 1000.0

    raise ValueError(f"Impossible de lire le volume depuis le nom de dossier : {name}")


def scan_dataset(root_dir: Path):
    items = []
    class_names = []
    if not root_dir.exists() or not root_dir.is_dir():
        raise RuntimeError(f"Dataset introuvable : {root_dir}")
    for class_dir in sorted(root_dir.iterdir()):
        if not class_dir.is_dir():
            continue
        class_name = class_dir.name
        class_names.append(class_name)
        for file_path in sorted(class_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            items.append((file_path, class_name))
    if len(items) == 0:
        raise RuntimeError(f"Aucune image trouvée dans {root_dir}")
    return items, sorted(set(class_names))


def get_default_workers():
    cpus = os.cpu_count() or 1
    return max(1, min(cpus - 1, 8))


def validate_args(args):
    if not 0.0 < args.test_size < 1.0:
        raise ValueError('test-size doit être entre 0 et 1.')
    if not 0.0 <= args.val_size < 1.0:
        raise ValueError('val-size doit être entre 0 et 1.')
    if args.test_size + args.val_size >= 1.0:
        raise ValueError('test-size et val-size doivent totaliser moins de 1.0.')
    if args.batch_size < 1:
        raise ValueError('batch-size doit être >= 1.')
    if args.workers < 0:
        raise ValueError('workers doit être >= 0.')


def load_checkpoint(model, checkpoint_path: Path, device):
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    print(f"Checkpoint chargé depuis {checkpoint_path}")
    return model


def build_transforms(image_size: int = 224):
    train_transform = A.Compose(
        [
            A.RandomResizedCrop(image_size, image_size, scale=(0.8, 1.0), ratio=(0.9, 1.1)),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.2),
            A.ShiftScaleRotate(shift_limit=0.08, scale_limit=0.12, rotate_limit=25, p=0.6),
            A.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15, hue=0.1, p=0.5),
            A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            ToTensorV2(),
        ]
    )
    val_transform = A.Compose(
        [
            A.Resize(image_size, image_size),
            A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            ToTensorV2(),
        ]
    )
    return train_transform, val_transform


class VolumeDataset(Dataset):
    def __init__(self, items, transform=None):
        self.items = items
        self.transform = transform

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        path, label = self.items[idx]
        image = np.array(Image.open(path).convert('RGB'))
        if self.transform:
            image = self.transform(image=image)['image']
        else:
            image = torch.from_numpy(image).permute(2, 0, 1).float() / 255.0
        return image, torch.tensor(label, dtype=torch.long)


def build_model(model_name: str = 'resnet50', num_classes: int = 4, pretrained: bool = True):
    if model_name == 'resnet18':
        model = models.resnet18(pretrained=pretrained)
        for param in model.parameters():
            param.requires_grad = False
        in_features = model.fc.in_features
        model.fc = nn.Sequential(
            nn.Linear(in_features, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.2),
            nn.Linear(256, num_classes),
        )
    elif model_name == 'resnet50':
        model = models.resnet50(pretrained=pretrained)
        for param in model.parameters():
            param.requires_grad = False
        in_features = model.fc.in_features
        model.fc = nn.Sequential(
            nn.Linear(in_features, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.2),
            nn.Linear(256, num_classes),
        )
    elif model_name == 'efficientnet_b0':
        model = models.efficientnet_b0(pretrained=pretrained)
        for param in model.parameters():
            param.requires_grad = False
        in_features = model.classifier[1].in_features
        model.classifier = nn.Sequential(
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(in_features, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(256, num_classes),
        )
    elif model_name == 'mobilenet_v3_small':
        model = models.mobilenet_v3_small(pretrained=pretrained)
        for param in model.parameters():
            param.requires_grad = False
        in_features = model.classifier[0].in_features
        model.classifier = nn.Sequential(
            nn.Linear(in_features, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.2),
            nn.Linear(256, num_classes),
        )
    else:
        raise ValueError(f"Model inconnu : {model_name}. Choix possibles: resnet18, resnet50, efficientnet_b0, mobilenet_v3_small")
    return model


def evaluate(model, loader, device, loss_fn):
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total_samples = 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            loss = loss_fn(outputs, labels)
            preds = outputs.argmax(dim=1)
            total_loss += loss.item() * images.size(0)
            total_correct += (preds == labels).sum().item()
            total_samples += images.size(0)
    return {
        'loss': total_loss / total_samples,
        'accuracy': total_correct / total_samples,
    }


def train_one_epoch(model, loader, optimizer, device, loss_fn):
    model.train()
    total_loss = 0.0
    total_samples = 0
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = loss_fn(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * images.size(0)
        total_samples += images.size(0)
    return total_loss / total_samples


def predict_all(model, loader, device):
    model.eval()
    y_true = []
    y_pred = []
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            preds = outputs.argmax(dim=1)
            y_true.extend(labels.cpu().numpy().tolist())
            y_pred.extend(preds.cpu().numpy().tolist())
    return y_true, y_pred


def save_confusion(output_dir: Path, matrix, class_names):
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / 'confusion_matrix.csv'
    with csv_path.open('w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([''] + class_names)
        for class_name, row in zip(class_names, matrix.tolist()):
            writer.writerow([class_name] + row)
    print(f"Matrice de confusion exportée : {csv_path}")
    return csv_path


def save_classification_report(output_dir: Path, report: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / 'classification_report.txt'
    report_path.write_text(report, encoding='utf-8')
    print(f"Classification report exporté : {report_path}")
    return report_path


def save_checkpoint(model, output_dir: Path, model_name: str, epoch: int, config: dict):
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / f"{model_name}_best.pth"
    torch.save({'model_state_dict': model.state_dict(), 'config': config}, checkpoint_path)
    config_path = output_dir / 'model_config.json'
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"Modèle enregistré dans : {checkpoint_path}")
    return checkpoint_path


def save_training_schema(output_dir: Path, config: dict, history: list, filename: str = 'training_schema.json'):
    output_dir.mkdir(parents=True, exist_ok=True)
    schema_path = output_dir / filename
    data = {
        'timestamp': datetime.now().isoformat(),
        'config': config,
        'history': history,
    }
    schema_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    csv_path = output_dir / 'training_metrics.csv'
    with csv_path.open('w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=['epoch', 'train_loss', 'val_loss', 'val_accuracy'])
        writer.writeheader()
        for row in history:
            writer.writerow(row)
    print(f"Schéma d'entraînement exporté : {schema_path}")
    print(f"Métriques CSV exportées : {csv_path}")
    return schema_path


def push_to_hf(output_dir: Path, repo_id: str):
    if not HF_AVAILABLE:
        raise RuntimeError("huggingface_hub n'est pas installé. Ajoute huggingface-hub à requirements et installe-le.")
    create_repo(repo_id, exist_ok=True)
    upload_file(
        path_or_fileobj=str(output_dir / 'model_config.json'),
        path_in_repo='model_config.json',
        repo_id=repo_id,
    )
    for file in output_dir.glob('*.pth'):
        upload_file(path_or_fileobj=str(file), path_in_repo=file.name, repo_id=repo_id)
    for file in output_dir.glob('*.json'):
        upload_file(path_or_fileobj=str(file), path_in_repo=file.name, repo_id=repo_id)
    print(f"Fichiers poussés vers Hugging Face : {repo_id}")


def parse_args():
    parser = argparse.ArgumentParser(description='Entraînement d\'un modèle de classification de volumes')
    parser.add_argument('--data-dir', type=Path, default=Path('dataset_eauTop'), help='Dossier racine du dataset')
    parser.add_argument('--model-name', type=str, default='resnet18', choices=['resnet18', 'resnet50', 'efficientnet_b0', 'mobilenet_v3_small'])
    parser.add_argument('--image-size', type=int, default=224)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--lr', type=float, default=2e-4)
    parser.add_argument('--weight-decay', type=float, default=1e-4)
    parser.add_argument('--output-dir', type=Path, default=Path('checkpoints'))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--test-size', type=float, default=0.2)
    parser.add_argument('--val-size', type=float, default=0.2)
    parser.add_argument('--workers', type=int, default=get_default_workers())
    parser.add_argument('--device', type=str, default='auto', choices=['auto', 'cpu', 'mps', 'cuda'], help='Device à utiliser pour l\'entraînement')
    parser.add_argument('--compile', action='store_true', help='Activer torch.compile pour accélérer l\'entraînement')
    parser.add_argument('--push-to-hub', action='store_true', help='Pousser le modèle vers Hugging Face Hub')
    parser.add_argument('--repo-id', type=str, default=None, help='Identifiant Hugging Face repo, ex: username/volume-estimator')
    parser.add_argument('--dataset-summary', action='store_true', help='Afficher un résumé du dataset (nombre d\'images par classe)')
    parser.add_argument('--pretrained', dest='pretrained', action='store_true', help='Charger un modèle pré-entraîné (par défaut)')
    parser.add_argument('--no-pretrained', dest='pretrained', action='store_false', help='Désactiver le pré-entraînement')
    parser.set_defaults(pretrained=True)
    parser.add_argument('--patience', type=int, default=5, help='Nombre d\'époques sans amélioration avant early stopping')
    parser.add_argument('--resume', type=Path, default=None, help='Reprendre l\'entraînement depuis un checkpoint existant')
    return parser.parse_args()


def get_device(device_arg: str):
    if device_arg == 'auto':
        if torch.backends.mps.is_available():
            return torch.device('mps')
        if torch.cuda.is_available():
            return torch.device('cuda')
        return torch.device('cpu')
    if device_arg == 'mps' and torch.backends.mps.is_available():
        return torch.device('mps')
    if device_arg == 'cuda' and torch.cuda.is_available():
        return torch.device('cuda')
    return torch.device('cpu')


def main():
    args = parse_args()
    validate_args(args)

    if args.dataset_summary:
        items, class_names = scan_dataset(args.data_dir)
        label_counts = Counter(label for _, label in items)
        print("Résumé du dataset :")
        for class_name in class_names:
            print(f"  {class_name}: {label_counts.get(class_name, 0)} images")
        print(f"  Total images : {len(items)}")
        return

    set_seed(args.seed)
    device = get_device(args.device)
    print(f"Device utilisé pour l'entraînement : {device}")

    items, class_names = scan_dataset(args.data_dir)
    label2idx = {class_name: idx for idx, class_name in enumerate(class_names)}
    items = [(path, label2idx[label]) for path, label in items]

    labels = [label for _, label in items]
    label_counts = Counter(labels)
    majority = max(label_counts.values())
    baseline_acc = majority / len(labels)
    majority_label = class_names[label_counts.most_common(1)[0][0]]
    print(f"Baseline constant sur la classe majoritaire ({majority_label}) : {baseline_acc*100:.1f}%")
    print(f"Classes : {class_names}")
    print(f"Images totales : {len(items)}")

    train_items, test_items = train_test_split(
        items,
        test_size=args.test_size,
        random_state=args.seed,
        stratify=labels,
    )
    val_ratio = args.val_size / (1.0 - args.test_size)
    val_items, train_items = train_test_split(
        train_items,
        test_size=1.0 - val_ratio,
        random_state=args.seed,
        stratify=[label for _, label in train_items],
    )

    train_transform, val_transform = build_transforms(args.image_size)
    train_dataset = VolumeDataset(train_items, transform=train_transform)
    val_dataset = VolumeDataset(val_items, transform=val_transform)
    test_dataset = VolumeDataset(test_items, transform=val_transform)

    pin_memory = device.type == 'cuda'
    generator = torch.Generator().manual_seed(args.seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.workers,
        pin_memory=pin_memory,
        generator=generator,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_memory,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_memory,
    )

    model = build_model(args.model_name, num_classes=len(class_names), pretrained=args.pretrained).to(device)
    if args.compile:
        try:
            model = torch.compile(model)
            print('torch.compile activé')
        except Exception as exc:
            print(f"Impossible d'activer torch.compile : {exc}")

    if args.resume is not None:
        if not args.resume.exists():
            raise FileNotFoundError(f"Checkpoint introuvable : {args.resume}")
        model = load_checkpoint(model, args.resume, device)

    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss()

    best_val_loss = float('inf')
    best_epoch = 0
    epochs_no_improve = 0
    history = []

    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(model, train_loader, optimizer, device, loss_fn)
        val_metrics = evaluate(model, val_loader, device, loss_fn)
        scheduler.step()

        history.append({
            'epoch': epoch,
            'train_loss': round(train_loss, 6),
            'val_loss': round(val_metrics['loss'], 6),
            'val_accuracy': round(val_metrics['accuracy'], 6),
        })

        print(
            f"Epoch {epoch}/{args.epochs} | train_loss={train_loss:.4f} | "
            f"val_loss={val_metrics['loss']:.4f} | val_acc={val_metrics['accuracy']*100:.2f}%"
        )

        if val_metrics['loss'] + 1e-6 < best_val_loss:
            best_val_loss = val_metrics['loss']
            best_epoch = epoch
            epochs_no_improve = 0
            config = {
                'model_name': args.model_name,
                'image_size': args.image_size,
                'num_classes': len(class_names),
                'classes': class_names,
                'output': ['class_label'],
                'pretrained': args.pretrained,
            }
            save_checkpoint(model, args.output_dir, args.model_name, epoch, config)
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= args.patience:
                print(f"Early stopping après {epoch} époques sans amélioration")
                break

    save_training_schema(args.output_dir, {
        'model_name': args.model_name,
        'image_size': args.image_size,
        'batch_size': args.batch_size,
        'epochs': epoch,
        'lr': args.lr,
        'weight_decay': args.weight_decay,
        'classes': class_names,
        'pretrained': args.pretrained,
        'device': str(device),
    }, history)

    test_metrics = evaluate(model, test_loader, device, loss_fn)
    print('--- Résultats sur le set de test ---')
    print(f"test_loss={test_metrics['loss']:.4f} | test_acc={test_metrics['accuracy']*100:.2f}%")

    y_true, y_pred = predict_all(model, test_loader, device)
    cm = confusion_matrix(y_true, y_pred)
    report = classification_report(y_true, y_pred, target_names=class_names, zero_division=0)
    print('--- Confusion matrix ---')
    print(cm)
    print('--- Classification report ---')
    print(report)
    save_confusion(output_dir=args.output_dir, matrix=cm, class_names=class_names)
    save_classification_report(output_dir=args.output_dir, report=report)

    if args.push_to_hub:
        if args.repo_id is None:
            raise ValueError('repo-id est requis pour --push-to-hub')
        push_to_hf(args.output_dir, args.repo_id)


if __name__ == '__main__':
    main()
