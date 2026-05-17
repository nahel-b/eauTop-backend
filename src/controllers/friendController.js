const mongoose = require('mongoose');
const User = require('../models/User');
const Friendship = require('../models/Friendship');
const WaterIntake = require('../models/WaterIntake');

// Search users by username
exports.searchUsers = async (req, res) => {
  try {
    const { query } = req.query;
    const currentUserId = req.userId;

    if (!query) {
      return res.status(400).json({ message: 'Search query required' });
    }

    // Find users matching the query, excluding current user
    const users = await User.find(
      {
        username: { $regex: query, $options: 'i' },
        _id: { $ne: currentUserId },
      },
      'username _id'
    ).limit(10);

    res.json(users);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

// Send friend request
exports.sendFriendRequest = async (req, res) => {
  try {
    const { requesteeId } = req.body;
    const requesterId = req.userId;

    if (requesterId === requesteeId) {
      return res.status(400).json({ message: 'Cannot send request to yourself' });
    }

    // Check if already friends or request exists
    const existing = await Friendship.findOne({
      $or: [
        { requester: requesterId, requestee: requesteeId },
        { requester: requesteeId, requestee: requesterId },
      ],
    });

    if (existing) {
      return res.status(400).json({ message: 'Friend request already exists' });
    }

    const friendship = new Friendship({
      requester: requesterId,
      requestee: requesteeId,
      status: 'pending',
    });

    await friendship.save();
    res.json({ message: 'Friend request sent', friendship });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

// Get pending friend requests
exports.getPendingRequests = async (req, res) => {
  try {
    const userId = req.userId;

    const requests = await Friendship.find({
      requestee: userId,
      status: 'pending',
    }).populate('requester', 'username _id');

    res.json(requests);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

// Accept friend request
exports.acceptFriendRequest = async (req, res) => {
  try {
    const { friendshipId } = req.body;
    const userId = req.userId;

    const friendship = await Friendship.findById(friendshipId);

    if (!friendship) {
      return res.status(404).json({ message: 'Friend request not found' });
    }

    if (friendship.requestee.toString() !== userId) {
      return res.status(403).json({ message: 'Unauthorized' });
    }

    friendship.status = 'accepted';
    friendship.updatedAt = Date.now();
    await friendship.save();

    res.json({ message: 'Friend request accepted', friendship });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

// Reject friend request
exports.rejectFriendRequest = async (req, res) => {
  try {
    const { friendshipId } = req.body;
    const userId = req.userId;

    const friendship = await Friendship.findById(friendshipId);

    if (!friendship) {
      return res.status(404).json({ message: 'Friend request not found' });
    }

    if (friendship.requestee.toString() !== userId) {
      return res.status(403).json({ message: 'Unauthorized' });
    }

    friendship.status = 'rejected';
    friendship.updatedAt = Date.now();
    await friendship.save();

    res.json({ message: 'Friend request rejected' });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

// Get friends list
exports.getFriends = async (req, res) => {
  try {
    const userId = req.userId;

    const friendships = await Friendship.find(
      {
        $or: [
          { requester: userId, status: 'accepted' },
          { requestee: userId, status: 'accepted' },
        ],
      }
    ).populate('requester requestee', 'username _id');

    // Extract friend objects from both directions
    const friends = friendships.map((f) => {
      return f.requester._id.toString() === userId ? f.requestee : f.requester;
    });

    res.json(friends);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

// Get friend data with stats
exports.getFriendStats = async (req, res) => {
  try {
    const { friendId } = req.params;
    const userId = req.userId;

    // Verify friendship exists
    const friendship = await Friendship.findOne({
      $or: [
        { requester: userId, requestee: friendId, status: 'accepted' },
        { requester: friendId, requestee: userId, status: 'accepted' },
      ],
    });

    if (!friendship) {
      return res.status(403).json({ message: 'Not friends' });
    }

    // Get friend's today intake
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const todayIntake = await WaterIntake.aggregate([
      {
        $match: {
          userId: new mongoose.Types.ObjectId(friendId),
          timestamp: { $gte: today },
        },
      },
      {
        $group: {
          _id: null,
          totalVolume: { $sum: '$actualVolume' },
          count: { $sum: 1 },
          waterIntakes: { $push: '$$ROOT' },
        },
      },
      {
        $project: {
          _id: 0,
          totalVolume: 1,
          count: 1,
          waterIntakes: 1,
        },
      },
    ]);

    // Get friend's history
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const history = await WaterIntake.aggregate([
      {
        $match: {
          userId: new mongoose.Types.ObjectId(friendId),
          timestamp: { $gte: thirtyDaysAgo },
        },
      },
      {
        $group: {
          _id: {
            $dateToString: { format: '%Y-%m-%d', date: '$timestamp' },
          },
          totalVolume: { $sum: '$actualVolume' },
          count: { $sum: 1 },
        },
      },
      { $sort: { _id: 1 } },
      {
        $project: {
          date: '$_id',
          totalVolume: 1,
          count: 1,
          _id: 0,
        },
      },
    ]);

    // Get friend's info
    const friend = await User.findById(friendId, 'username _id');

    res.json({
      friend,
      todayIntake: todayIntake[0] || { totalVolume: 0, count: 0, waterIntakes: [] },
      history: { dailyTotals: history },
    });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

// Remove friend
exports.removeFriend = async (req, res) => {
  try {
    const { friendId } = req.params;
    const userId = req.userId;

    const friendship = await Friendship.findOneAndDelete({
      $or: [
        { requester: userId, requestee: friendId, status: 'accepted' },
        { requester: friendId, requestee: userId, status: 'accepted' },
      ],
    });

    if (!friendship) {
      return res.status(404).json({ message: 'Friendship not found' });
    }

    res.json({ message: 'Friend removed' });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};
