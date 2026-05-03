import argparse
from pathlib import Path

try:
    from huggingface_hub import create_repo, upload_file, HfApi,login
except ImportError:
    raise ImportError('Installe huggingface-hub avec `pip install huggingface-hub` pour utiliser ce script.')


def collect_files(output_dir: Path):
    files = []
    for suffix in ['*.pth', 'model_config.json', 'training_schema.json', 'training_metrics.csv', 'confusion_matrix.csv', 'classification_report.txt']:
        files.extend(sorted(output_dir.glob(suffix)))
    return files


def push_files(repo_id: str, output_dir: Path, private: bool = False, token: str | None = None):
    api = HfApi()
    create_repo(repo_id, exist_ok=True, private=private, token=token)
    files = collect_files(output_dir)
    if len(files) == 0:
        raise FileNotFoundError(f"Aucun fichier trouvé dans {output_dir} pour pousser vers Hugging Face.")
    for file_path in files:
        branch_path = file_path.name
        upload_file(
            path_or_fileobj=str(file_path),
            path_in_repo=branch_path,
            repo_id=repo_id,
            token=token,
            repo_type='model',
            create_pr=False,
        )
        print(f"Poussé : {file_path.name}")
    print(f"Tous les fichiers ont été poussés vers {repo_id}")


def parse_args():
    parser = argparse.ArgumentParser(description='Pousser un modèle et ses artefacts vers Hugging Face Hub')
    parser.add_argument('--repo-id', type=str, required=True, help='Identifiant du repo Hugging Face (ex: username/volume-estimator)')
    parser.add_argument('--output-dir', type=Path, default=Path('checkpoints'), help='Dossier contenant le checkpoint et les fichiers associés')
    parser.add_argument('--private', action='store_true', help='Créer le repo comme privé')
    parser.add_argument('--token', type=str, default=None, help='Token Hugging Face (optionnel si déjà connecté)')
    return parser.parse_args()


def main():
    login()
    args = parse_args()
    output_dir = args.output_dir
    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {output_dir}")

    push_files(repo_id=args.repo_id, output_dir=output_dir, private=args.private, token=args.token)


if __name__ == '__main__':
    main()
