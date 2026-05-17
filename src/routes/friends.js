const express = require('express');
const router = express.Router();
const friendController = require('../controllers/friendController');
const auth = require('../middleware/auth');

// Protected routes
router.get('/search', auth, friendController.searchUsers);
router.post('/request', auth, friendController.sendFriendRequest);
router.get('/requests', auth, friendController.getPendingRequests);
router.put('/request/accept', auth, friendController.acceptFriendRequest);
router.put('/request/reject', auth, friendController.rejectFriendRequest);
router.get('/list', auth, friendController.getFriends);
router.get('/:friendId/stats', auth, friendController.getFriendStats);
router.delete('/:friendId', auth, friendController.removeFriend);

module.exports = router;
