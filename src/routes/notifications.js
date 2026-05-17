const express = require('express');
const notificationController = require('../controllers/notificationController');
const auth = require('../middleware/auth');

const router = express.Router();

// Protected routes (require authentication)
router.post('/subscribe', auth, notificationController.subscribeToPush);
router.post('/unsubscribe', auth, notificationController.unsubscribeFromPush);
router.get('/settings', auth, notificationController.getNotificationSettings);
router.put('/settings', auth, notificationController.updateNotificationSettings);

// Public cron job route (secured by token)
router.post('/cron/check', notificationController.checkWaterIntakeAndNotify);

module.exports = router;
