const User = require('../models/User');
const WaterIntake = require('../models/WaterIntake');
const webpush = require('web-push');

webpush.setVapidDetails(
  process.env.VAPID_SUBJECT || 'mailto:example@example.com',
  process.env.VAPID_PUBLIC_KEY,
  process.env.VAPID_PRIVATE_KEY
);

// Subscribe to push notifications
exports.subscribeToPush = async (req, res) => {
  try {
    const { subscription } = req.body;

    if (!subscription || !subscription.endpoint) {
      return res.status(400).json({ error: 'Invalid subscription' });
    }

    const user = await User.findByIdAndUpdate(
      req.userId,
      {
        'notificationSettings.pushSubscription': subscription,
        'notificationSettings.enabled': true,
      },
      { new: true }
    );

    res.json({
      message: 'Subscribed to notifications',
      notificationSettings: user.notificationSettings
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

// Unsubscribe from push notifications
exports.unsubscribeFromPush = async (req, res) => {
  try {
    const user = await User.findByIdAndUpdate(
      req.userId,
      {
        'notificationSettings.enabled': false,
        'notificationSettings.pushSubscription': null,
      },
      { new: true }
    );

    res.json({
      message: 'Unsubscribed from notifications',
      notificationSettings: user.notificationSettings
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

// Get notification settings
exports.getNotificationSettings = async (req, res) => {
  try {
    const user = await User.findById(req.userId).select('notificationSettings');
    res.json(user.notificationSettings);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

// Update notification settings
exports.updateNotificationSettings = async (req, res) => {
  try {
    const { notifyAtNoon, notifyAtEvening } = req.body;

    const updateData = {};
    if (notifyAtNoon) {
      updateData['notificationSettings.notifyAtNoon'] = notifyAtNoon;
    }
    if (notifyAtEvening) {
      updateData['notificationSettings.notifyAtEvening'] = notifyAtEvening;
    }

    const user = await User.findByIdAndUpdate(
      req.userId,
      updateData,
      { new: true }
    );

    res.json({
      message: 'Settings updated',
      notificationSettings: user.notificationSettings
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};

// Cron job: Check water intake and send notifications
exports.checkWaterIntakeAndNotify = async (req, res) => {
  try {
    // Verify cron job authenticity (optional - use header token)
    const cronToken = req.headers['x-cron-token'];
    if (cronToken !== process.env.CRON_SECRET_TOKEN) {
      return res.status(401).json({ error: 'Unauthorized cron job' });
    }

    const now = new Date();
    const hours = now.getHours();

    // Get all users with enabled notifications
    const users = await User.find({
      'notificationSettings.enabled': true,
      'notificationSettings.pushSubscription': { $exists: true },
    }).lean();

    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);
    const endOfDay = new Date();
    endOfDay.setHours(23, 59, 59, 999);

    let sentCount = 0;
    const goalPerDay = 2000; // 2 liters

    for (const user of users) {
      const waterIntakes = await WaterIntake.find({
        userId: user._id,
        timestamp: { $gte: startOfDay, $lte: endOfDay },
      });

      const totalVolume = waterIntakes.reduce((sum, intake) => sum + intake.actualVolume, 0);
      const percentage = (totalVolume / goalPerDay) * 100;

      let shouldNotify = false;
      let message = {};

      // At 12h: Check if less than 50%
      if (hours >= 12 && hours < 13 && user.notificationSettings.notifyAtNoon?.enabled) {
        if (percentage < (user.notificationSettings.notifyAtNoon?.threshold || 50)) {
          shouldNotify = true;
          message = {
            title: '💧 Hydratation à midi',
            body: `Vous n'avez consommé que ${Math.round(percentage)}% de votre objectif (${totalVolume}mL / ${goalPerDay}mL). N'oubliez pas de boire!`,
          };
        }
      }

      // At 20h: Check if less than 80%
      if (hours >= 20 && hours < 21 && user.notificationSettings.notifyAtEvening?.enabled) {
        if (percentage < (user.notificationSettings.notifyAtEvening?.threshold || 80)) {
          shouldNotify = true;
          message = {
            title: '💧 Hydratation du soir',
            body: `Vous n'avez consommé que ${Math.round(percentage)}% de votre objectif (${totalVolume}mL / ${goalPerDay}mL). Finissez votre journée bien hydraté!`,
          };
        }
      }

      if (shouldNotify && user.notificationSettings.pushSubscription) {
        try {
          await webpush.sendNotification(
            user.notificationSettings.pushSubscription,
            JSON.stringify(message)
          );
          sentCount++;
        } catch (error) {
          console.error(`Failed to send notification to user ${user._id}:`, error.message);
          // If subscription is invalid, remove it
          if (error.statusCode === 410) {
            await User.findByIdAndUpdate(user._id, {
              'notificationSettings.pushSubscription': null,
              'notificationSettings.enabled': false,
            });
          }
        }
      }
    }

    res.json({
      message: 'Cron job completed',
      time: `${hours}h`,
      notificationsSent: sentCount,
      totalUsers: users.length,
    });
  } catch (error) {
    console.error('Cron job error:', error);
    res.status(500).json({ error: error.message });
  }
};
