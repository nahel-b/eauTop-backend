const express = require('express');
const router = express.Router();
const authController = require('../controllers/authController');

// Public routes
router.post('/register', authController.register);
router.post('/login', authController.login);

// Protected routes (these would require auth middleware)
// These are handled in the main app.js with middleware

module.exports = router;
