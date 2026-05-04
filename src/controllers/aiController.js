const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');

// Mapping of class names from the model to readable names and default volumes
const CLASS_MAPPING = {
  '01_verre_200mL': {
    name: 'Verre',
    defaultVolume: 200,
    variants: [100, 150, 200, 250],
  },
  '02_tasse_400mL': {
    name: 'Tasse',
    defaultVolume: 400,
    variants: [200, 300, 400, 500],
  },
  '03_bouteille_500mL': {
    name: 'Bouteille',
    defaultVolume: 500,
    variants: [250, 350, 500, 750],
  },
  '04_bouteille_1L': {
    name: 'Bouteille',
    defaultVolume: 1000,
    variants: [500, 1000, 1500, 2000],
  },
  '05_bouteille_1L5': {
    name: 'Bouteille',
    defaultVolume: 1500,
    variants: [500, 1000, 1500, 2000],
  },
};

// Predict container from image
exports.predictContainer = async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No image provided' });
    }


    const imagePath = req.file.path;
    // Utilise le chemin absolu depuis la racine du projet (Render context)
    const checkpointPath = path.join(process.cwd(), 'volume-estimation/checkpoints/resnet50_best.pth');
    const pythonScript = path.join(process.cwd(), 'volume-estimation/predict.py');

    execFile(
      'python3',
      [
        pythonScript,
        '--checkpoint',
        checkpointPath,
        '--image',
        imagePath,
        '--model-name',
        'resnet50',
        '--image-size',
        '224',
        '--device',
        'cpu',
      ],
      (error, stdout, stderr) => {
        // Clean up temp file
        if (fs.existsSync(imagePath)) {
          fs.unlinkSync(imagePath);
        }

        if (error) {
          console.error('Python error:', stderr);
          return res.status(500).json({ error: 'Prediction failed' });
        }

        const predictedClass = stdout.trim().split('\n').pop().split(': ')[1];
        const classInfo = CLASS_MAPPING[predictedClass] || {
          name: predictedClass,
          defaultVolume: 500,
          variants: [250, 500, 750, 1000],
        };

        res.json({
          predictedClass,
          containerName: classInfo.name,
          estimatedVolume: classInfo.defaultVolume,
          variants: classInfo.variants,
        });
      }
    );
  } catch (error) {
    // Clean up temp file if it exists
    if (req.file && fs.existsSync(req.file.path)) {
      fs.unlinkSync(req.file.path);
    }
    res.status(500).json({ error: error.message });
  }
};
