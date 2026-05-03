import argparse
from pathlib import Path

import torch

#python export_onnx.py --checkpoint checkpoints/resnet18_best.pth --model-name resnet18 --output model_resnet18.onnx 

try:
    from train import build_model, load_checkpoint
except ImportError as exc:
    raise ImportError('Impossible d\'importer build_model depuis train.py : ' + str(exc))

try:
    from onnxruntime_tools import optimizer
    ONNX_RUNTIME_TOOLS_AVAILABLE = True
except ImportError:
    ONNX_RUNTIME_TOOLS_AVAILABLE = False


def parse_args():
    parser = argparse.ArgumentParser(description='Exporter un modèle PyTorch en ONNX et optimiser le fichier ONNX')
    parser.add_argument('--checkpoint', type=Path, required=True, help='Chemin du checkpoint .pth')
    parser.add_argument('--output', type=Path, default=Path('model.onnx'), help='Chemin de sortie ONNX')
    parser.add_argument('--model-name', type=str, default='resnet50', choices=['resnet18', 'resnet50', 'efficientnet_b0', 'mobilenet_v3_small'])
    parser.add_argument('--image-size', type=int, default=224, help='Taille de l\'image en pixels')
    parser.add_argument('--device', type=str, default='cpu', choices=['cpu', 'cuda', 'mps'])
    parser.add_argument('--no-optimize', action='store_true', help='Désactiver l\'optimisation ONNX')
    return parser.parse_args()


def get_device(device_name: str):
    if device_name == 'cuda' and torch.cuda.is_available():
        return torch.device('cuda')
    if device_name == 'mps' and torch.backends.mps.is_available():
        return torch.device('mps')
    return torch.device('cpu')


def export_onnx(model, output_path: Path, image_size: int, device):
    model.eval()
    dummy_input = torch.randn(1, 3, image_size, image_size, device=device)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        opset_version=11,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={
            'input': {0: 'batch_size'},
            'output': {0: 'batch_size'},
        },
    )
    print(f'Fichier ONNX exporté : {output_path}')


def optimize_onnx(model_path: Path, optimized_path: Path):
    if not ONNX_RUNTIME_TOOLS_AVAILABLE:
        print('onnxruntime-tools n\'est pas installé, optimisation ONNX désactivée.')
        return False

    optimized_model = optimizer.optimize_model(str(model_path))
    optimized_model.save_model_to_file(str(optimized_path))
    print(f'Fichier ONNX optimisé : {optimized_path}')
    return True


def infer_num_classes(checkpoint_path: Path):
    checkpoint = torch.load(checkpoint_path, map_location='cpu')
    config = checkpoint.get('config') if isinstance(checkpoint, dict) else None
    if config and isinstance(config, dict) and 'num_classes' in config:
        return int(config['num_classes'])

    state_dict = checkpoint.get('model_state_dict', checkpoint)
    candidate_keys = [
        'fc.3.weight',
        'model.fc.3.weight',
        'module.fc.3.weight',
        'module.model.fc.3.weight',
    ]
    for key in candidate_keys:
        if key in state_dict:
            return int(state_dict[key].shape[0])

    raise RuntimeError('Impossible de déterminer num_classes depuis le checkpoint. Utilise --num-classes ou fournis un checkpoint avec config.')


def main():
    args = parse_args()
    device = get_device(args.device)

    num_classes = infer_num_classes(args.checkpoint)
    model = build_model(args.model_name, num_classes=num_classes, pretrained=True).to(device)
    model = load_checkpoint(model, args.checkpoint, device)

    export_onnx(model, args.output, args.image_size, device)

    if not args.no_optimize:
        optimized_output = args.output.parent / f'{args.output.stem}_optimized{args.output.suffix}'
        optimize_onnx(args.output, optimized_output)


if __name__ == '__main__':
    main()
