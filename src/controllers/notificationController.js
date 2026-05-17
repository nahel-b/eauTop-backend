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
        // Ensure default notification settings exist
        'notificationSettings.notifyAtNoon': {
          enabled: true,
          threshold: 50,
        },
        'notificationSettings.notifyAtEvening': {
          enabled: true,
          threshold: 80,
        },
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

// Send custom notification to a friend
exports.sendFriendNotification = async (req, res) => {
  try {
    const { friendId, message } = req.body;

    if (!friendId) {
      return res.status(400).json({ error: 'Friend ID required' });
    }

    const friend = await User.findById(friendId).select('notificationSettings username');
    if (!friend) {
      return res.status(404).json({ error: 'Friend not found' });
    }

    if (!friend.notificationSettings?.enabled || !friend.notificationSettings?.pushSubscription?.endpoint) {
      return res.status(400).json({ error: 'Friend has not enabled notifications' });
    }

    const sender = await User.findById(req.userId).select('username');

    const notificationPayload = {
      title: `💧 ${sender.username} t'envoie un message!`,
      body: message || `${sender.username} te rappelle de boire de l'eau! 💧`,
    };

    try {
      await webpush.sendNotification(
        friend.notificationSettings.pushSubscription,
        JSON.stringify(notificationPayload)
      );

      res.json({
        message: 'Notification sent to friend',
        sentTo: friend.username,
      });
    } catch (error) {
      console.error(`Failed to send notification to friend ${friendId}:`, error.message);
      if (error.statusCode === 410) {
        await User.findByIdAndUpdate(friendId, {
          'notificationSettings.pushSubscription': null,
          'notificationSettings.enabled': false,
        });
        return res.status(400).json({ error: 'Friend subscription expired' });
      }
      throw error;
    }
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};
  try {
    // Verify cron job authenticity (optional - use header token)
    const cronToken = req.headers['x-cron-token'];
    if (cronToken !== process.env.CRON_SECRET_TOKEN) {
      return res.status(401).json({ error: 'Unauthorized cron job' });
    }

    const now = new Date();
    const hours = now.getHours();

    console.log(`[CRON] Starting at ${hours}h...`);

    // Get all users with enabled notifications and valid push subscription
    const users = await User.find({
      'notificationSettings.enabled': true,
      'notificationSettings.pushSubscription.endpoint': { $exists: true, $ne: null },
    }).lean();

    console.log(`[CRON] Found ${users.length} users with notifications enabled`);

    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);
    const endOfDay = new Date();
    endOfDay.setHours(23, 59, 59, 999);

    let sentCount = 0;
    let skippedCount = 0;
    const goalPerDay = 2000; // 2 liters

    for (const user of users) {
      try {
        const waterIntakes = await WaterIntake.find({
          userId: user._id,
          timestamp: { $gte: startOfDay, $lte: endOfDay },
        });

        const totalVolume = waterIntakes.reduce((sum, intake) => sum + intake.actualVolume, 0);
        const percentage = (totalVolume / goalPerDay) * 100;

        console.log(`[CRON] User ${user._id}: ${Math.round(percentage)}% - Settings:`, {
          notifyAtNoon: user.notificationSettings?.notifyAtNoon,
          notifyAtEvening: user.notificationSettings?.notifyAtEvening,
        });

        let shouldNotify = false;
        let message = {};

        // At 12h: Check if less than 50%
        if (hours >= 12 && hours < 13) {
          const noonSettings = user.notificationSettings?.notifyAtNoon;
          if (noonSettings?.enabled && percentage < (noonSettings?.threshold || 50)) {
            console.log(`[CRON] User ${user._id}: Sending noon notification (${Math.round(percentage)}% < ${noonSettings?.threshold || 50}%)`);
            shouldNotify = true;
            message = {
              title: '💧 Hydratation à midi',
              body: `Vous n'avez consommé que ${Math.round(percentage)}% de votre objectif (${totalVolume}mL / ${goalPerDay}mL). N'oubliez pas de boire!`,
            };
          }
        }

        // At 20h: Check if less than 80%
        if (hours >= 20 && hours < 21) {
          const eveningSettings = user.notificationSettings?.notifyAtEvening;
          if (eveningSettings?.enabled && percentage < (eveningSettings?.threshold || 80)) {
            console.log(`[CRON] User ${user._id}: Sending evening notification (${Math.round(percentage)}% < ${eveningSettings?.threshold || 80}%)`);
            shouldNotify = true;
            message = {
              title: '💧 Hydratation du soir',
              body: `Vous n'avez consommé que ${Math.round(percentage)}% de votre objectif (${totalVolume}mL / ${goalPerDay}mL). Finissez votre journée bien hydraté!`,
            };
          }
        }

        if (shouldNotify && user.notificationSettings.pushSubscription?.endpoint) {
          try {
            await webpush.sendNotification(
              user.notificationSettings.pushSubscription,
              JSON.stringify(message)
            );
            sentCount++;
            console.log(`[CRON] ✓ Notification sent to user ${user._id}`);
          } catch (error) {
            console.error(`[CRON] Failed to send notification to user ${user._id}:`, error.message);
            // If subscription is invalid, remove it
            if (error.statusCode === 410) {
              await User.findByIdAndUpdate(user._id, {
                'notificationSettings.pushSubscription': null,
                'notificationSettings.enabled': false,
              });
            }
          }
        } else {
          if (!shouldNotify) {
            skippedCount++;
          }
        }
      } catch (error) {
        console.error(`[CRON] Error processing user ${user._id}:`, error.message);
      }
    }

    res.json({
      message: 'Cron job completed',
      time: `${hours}h`,
      notificationsSent: sentCount,
      usersSkipped: skippedCount,
      totalUsers: users.length,
    });
  } catch (error) {
    console.error('Cron job error:', error);
    res.status(500).json({ error: error.message });
  }
};
