# Volume Estimation

Ce projet entraîne un modèle de régression de volume à partir d'images de contenants.

## Structure attendue

Le dataset doit être organisé par dossier de classes, avec le volume dans le nom du dossier :

- `dataset_eauTop/01_verre_200mL/`
- `dataset_eauTop/02_tasse_400mL/`
- `dataset_eauTop/03_bouteille_500mL/`
- `dataset_eauTop/04_bouteille_1L5/`

Les images doivent être dans ces sous-dossiers.

## Installation

Pour le backend qui exécute uniquement un modèle ONNX, installe les dépendances légères :

```bash
cd /Users/nahelbelmadani/Desktop/projets/eauTop-backend/volume-estimation
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Si tu veux entraîner ou exporter le modèle depuis ce dépôt, installe les dépendances complètes :

```bash
python3 -m pip install -r requirements-full.txt
```

## Entraînement

1. Active ton environnement virtuel :

```bash
cd /Users/nahelbelmadani/Desktop/projets/eauTop-backend/volume-estimation
source .venv/bin/activate
```

2. Lance l'entraînement :

```bash
python train.py --data-dir dataset_eauTop --model-name resnet50 --epochs 25 --batch-size 16 --output-dir checkpoints
```

## Prédiction

Pour exécuter un modèle ONNX depuis le backend :

```bash
python predict.py --onnx-model model_resnet50.onnx --image dataset_eauTop/01_verre_500mL/IMG_7318.jpeg
```

Pour utiliser un checkpoint PyTorch (si tu as besoin de cela) :

```bash
python predict.py --checkpoint checkpoints/resnet50_best.pth --image dataset_eauTop/01_verre_200mL/IMG_7250.jpeg --model-name resnet50
```

La sortie affichera la classe prédite, par exemple `01_verre_200mL`.

## Hugging Face

Le modèle est compatible PyTorch et peut être poussé sur Hugging Face Hub.

1. Installe `huggingface-hub` :

```bash
pip install huggingface-hub
```

2. Connecte-toi :

```bash
huggingface-cli login
```

3. Lance l'entraînement avec publication :

```bash
python train.py --data-dir dataset_eauTop --model-name resnet50 --push-to-hub --repo-id ton-username/volume-estimator
```

## Déploiement

### A. Hugging Face Spaces

Tu peux ensuite créer un Space Gradio/Flask et charger `checkpoints/resnet50_best.pth`.

### B. Inference API

En exportant le checkpoint sur un repo Hugging Face, tu peux aussi le déployer via l'API d'inférence en créant un endpoint ou en utilisant un Space dédié.
