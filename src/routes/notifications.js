const express = require('express');
const notificationController = require('../controllers/notificationController');
const auth = require('../middleware/auth');
const User = require('../models/User');

const router = express.Router();

// Protected routes (require authentication)
router.post('/subscribe', auth, notificationController.subscribeToPush);
router.post('/unsubscribe', auth, notificationController.unsubscribeFromPush);
router.get('/settings', auth, notificationController.getNotificationSettings);
router.put('/settings', auth, notificationController.updateNotificationSettings);
router.post('/send-to-friend', auth, notificationController.sendFriendNotification);

// Public cron job route (secured by token)
router.post('/cron/check', notificationController.checkWaterIntakeAndNotify);

// Debug route - see your notification settings
router.get('/debug', auth, async (req, res) => {
  try {
    const user = await User.findById(req.userId).select('notificationSettings');
    res.json({
      message: 'Your notification settings',
      notificationSettings: user.notificationSettings,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

