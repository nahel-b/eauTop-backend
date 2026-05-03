const express = require('express');
const router = express.Router();
const waterController = require('../controllers/waterController');
const auth = require('../middleware/auth');

// Protected routes
router.post('/add', auth, waterController.addWater);
router.get('/today', auth, waterController.getTodayIntake);
router.get('/history', auth, waterController.getHistory);
router.delete('/:id', auth, waterController.deleteIntake);

module.exports = router;
