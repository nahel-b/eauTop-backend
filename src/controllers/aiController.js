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
    const onnxModelPath = path.join(process.cwd(), 'volume-estimation/model_resnet50.onnx');
    const pythonScript = path.join(process.cwd(), 'volume-estimation/predict.py');

    console.log('AI prediction request', {
      imagePath,
      onnxModelPath,
    });

    execFile(
      'python3',
      [
        pythonScript,
        '--onnx-model',
        onnxModelPath,
        '--image',
        imagePath,
        '--image-size',
        '224',
      ],
      (error, stdout, stderr) => {
        // Clean up temp file
        if (fs.existsSync(imagePath)) {
          fs.unlinkSync(imagePath);
        }

        if (stderr) {
          console.warn('Python stderr:', stderr.trim());
        }

        if (error) {
          console.error('Python error:', stderr);
          return res.status(500).json({ error: 'Prediction failed' });
        }

        let prediction;
        try {
          prediction = JSON.parse(stdout.trim().split('\n').pop());
        } catch (parseError) {
          console.error('Failed to parse prediction output:', stdout, parseError);
          return res.status(500).json({ error: 'Invalid prediction response' });
        }

        const predictedClass = prediction.predicted_class;
        const confidence = Number(prediction.confidence ?? 0);
        const classInfo = CLASS_MAPPING[predictedClass] || {
          name: predictedClass,
          defaultVolume: 500,
          variants: [250, 500, 750, 1000],
        };

        console.log('AI prediction result', {
          predictedClass,
          confidence,
          containerName: classInfo.name,
        });

        res.json({
          predictedClass,
          confidence,
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
