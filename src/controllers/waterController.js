const WaterIntake = require('../models/WaterIntake');

// Add water intake record
exports.addWater = async (req, res) => {
  try {
    const { containerType, estimatedVolume, actualVolume } = req.body;

    if (!containerType || !estimatedVolume || !actualVolume) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    const waterIntake = new WaterIntake({
      userId: req.userId,
      containerType,
      estimatedVolume,
      actualVolume,
    });

    await waterIntake.save();

    res.status(201).json({
      message: 'Water intake recorded',
      data: waterIntake,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

// Get user's water intake for today
exports.getTodayIntake = async (req, res) => {
  try {
    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);

    const endOfDay = new Date();
    endOfDay.setHours(23, 59, 59, 999);

    const waterIntakes = await WaterIntake.find({
      userId: req.userId,
      timestamp: {
        $gte: startOfDay,
        $lte: endOfDay,
      },
    }).sort({ timestamp: -1 });

    const totalVolume = waterIntakes.reduce((sum, intake) => sum + intake.actualVolume, 0);

    res.json({
      totalVolume,
      waterIntakes,
      goal: 2000, // 2 liters per day
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

// Get water intake history (last 30 days)
exports.getHistory = async (req, res) => {
  try {
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const waterIntakes = await WaterIntake.find({
      userId: req.userId,
      timestamp: { $gte: thirtyDaysAgo },
    }).sort({ timestamp: -1 });

    // Group by day
    const groupedByDay = {};
    waterIntakes.forEach((intake) => {
      const date = new Date(intake.timestamp).toISOString().split('T')[0];
      if (!groupedByDay[date]) {
        groupedByDay[date] = [];
      }
      groupedByDay[date].push(intake);
    });

    // Calculate daily totals
    const dailyTotals = Object.entries(groupedByDay).map(([date, intakes]) => ({
      date,
      totalVolume: intakes.reduce((sum, intake) => sum + intake.actualVolume, 0),
      count: intakes.length,
    }));

    res.json({
      dailyTotals: dailyTotals.sort((a, b) => new Date(b.date) - new Date(a.date)),
      totalIntakes: waterIntakes.length,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

// Delete water intake record
exports.deleteIntake = async (req, res) => {
  try {
    const { id } = req.params;

    const waterIntake = await WaterIntake.findById(id);
    if (!waterIntake) {
      return res.status(404).json({ error: 'Water intake not found' });
    }

    if (waterIntake.userId.toString() !== req.userId) {
      return res.status(403).json({ error: 'Not authorized' });
    }

    await WaterIntake.findByIdAndDelete(id);
    res.json({ message: 'Water intake deleted' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};
