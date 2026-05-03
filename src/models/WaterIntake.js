const mongoose = require('mongoose');

const waterIntakeSchema = new mongoose.Schema(
  {
    userId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    containerType: {
      type: String,
      required: true, // 'verre', 'tasse', 'bouteille_500ml', 'bouteille_1l', 'bouteille_1l5'
    },
    estimatedVolume: {
      type: Number,
      required: true, // in ml
    },
    actualVolume: {
      type: Number,
      required: true, // in ml - can be adjusted by user
    },
    timestamp: {
      type: Date,
      default: Date.now,
    },
    imageUrl: {
      type: String,
    },
  },
  { timestamps: true }
);

module.exports = mongoose.model('WaterIntake', waterIntakeSchema);
