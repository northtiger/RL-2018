import sys
sys.dont_write_bytecode = True

import gym
import numpy as np
import tensorflow as tf
import random
import os
import subprocess
import architectures as arch
import learning_rates as lrng
import explore_rates as expl
import replay_memory as rplm

DIR_PATH = os.path.dirname(os.path.realpath(__file__)) + "/logs"


def pause():
    programPause = raw_input("Press the <ENTER> key to continue...")


class DQN_Agent:
    # architecture, explore_rate and learning_rate are strings, see respective files for definitions

    def __init__(self, environment, architecture, explore_rate, learning_rate):
        self.env = environment
        self.episodes_trained = 0
        self.architecture = arch.arch_dict[architecture]
        self.explore_rate = expl.expl_dict[explore_rate]()
        self.learning_rate = lrng.lrng_dict[learning_rate]()
        self.initialize_tf_variables()

    def set_training_parameters(self, discount, batch_size, memory_capacity, num_episodes):
        self.discount = discount
        self.replay_memory = rplm.Replay_Memory(memory_capacity, batch_size)
        self.num_episodes = num_episodes

    def initialize_tf_variables(self):
        # Setting up game specific variables
        self.state_size = self.env.state_space_size
        self.lower_bounds = self.env.state_space_lower_bounds
        self.upper_bounds = self.env.state_space_upper_bounds
        self.action_size = self.env.action_space_size
        self.q_grid = None

        # Tf placeholders
        self.state_tf = tf.placeholder(shape=[None, self.state_size], dtype=tf.float64)
        self.action_tf = tf.placeholder(shape=[None, self.action_size], dtype=tf.float64)
        self.y_tf = tf.placeholder(dtype=tf.float64)
        self.alpha = tf.placeholder(dtype=tf.float64)
        self.training_score = tf.placeholder(dtype=tf.float64)
        self.avg_q = tf.placeholder(dtype=tf.float64)

        # Operations
        self.Q_value = self.architecture(self.state_tf, self.action_size)
        self.Q_argmax = tf.argmax(self.Q_value[0])
        self.Q_amax = tf.reduce_max(self.Q_value[0])
        self.Q_value_at_action = tf.reduce_sum(tf.multiply(self.Q_value, self.action_tf), axis=1)

        # Training related
        self.loss = tf.reduce_mean(tf.square(self.y_tf - self.Q_value_at_action))
        self.train_op = tf.train.AdamOptimizer(learning_rate=self.alpha).minimize(self.loss)
        self.fixed_weights = None

        # Tensorflow session setup
        config = tf.ConfigProto()
        config.allow_soft_placement = True
        config.gpu_options.allow_growth = True
        config.log_device_placement = False
        self.sess = tf.Session(config=config)
        self.trainable_variables = tf.trainable_variables()

        # Tensorboard setup
        self.writer = tf.summary.FileWriter(DIR_PATH)
        self.writer.add_graph(self.sess.graph)
        tf.summary.scalar("Training score", self.training_score, collections=None, family=None)
        tf.summary.scalar("Average Q-value", self.avg_q, collections=None, family=None)
        self.run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
        self.run_metadata = tf.RunMetadata()
        self.summary = tf.summary.merge_all()
        subprocess.Popen(['tensorboard', '--logdir', DIR_PATH])

        # Initialising and finalising
        self.sess.run(tf.global_variables_initializer())
        self.sess.graph.finalize()

    def experience_replay(self, save_metadata):
        state_batch, action_batch, reward_batch, next_state_batch, done_batch = self.replay_memory.get_batch()
        y_batch = [None] * self.replay_memory.batch_size

        dict = {self.state_tf: next_state_batch}
        dict.update(zip(self.trainable_variables, self.fixed_weights))
        Q_value_batch = self.sess.run(self.Q_value, feed_dict=dict)

        for i in range(self.replay_memory.batch_size):
            y_batch[i] = reward_batch[i] + (0 if done_batch[i] else self.discount * np.max(Q_value_batch[i]))

        if not save_metadata:
            self.sess.run(self.train_op, feed_dict={self.y_tf: y_batch, self.action_tf: action_batch, self.state_tf: state_batch,
                                                    self.alpha: self.learning_rate.get(self.episodes_trained, self.num_episodes)})
        else:
            self.sess.run(self.train_op, feed_dict={self.y_tf: y_batch, self.action_tf: action_batch, self.state_tf: state_batch, 
                                                    self.alpha: self.learning_rate.get(self.episodes_trained, self.num_episodes)},
                                                    options=self.run_options, run_metadata=self.run_metadata)

    def get_action(self, state, epsilon):
        if random.random() < epsilon:
            return self.env.sample_action_space()
        else:
            return self.sess.run(self.Q_argmax, feed_dict={self.state_tf: [state]})

    def update_fixed_weights(self):
        self.fixed_weights = self.sess.run(self.trainable_variables)

    def train(self):
        for episode in range(self.num_episodes):
            state = self.env.reset()
            done = False
            self.update_fixed_weights()
            save_metadata = episode == 100
            while not done:
                # Take action, update replay memory and update history (for storing previous 4 frames for example)
                action = self.get_action(state, self.explore_rate.get(self.episodes_trained, self.num_episodes))
                next_state, reward, done, _ = self.env.step(action)
                self.replay_memory.add(self.env, state, action, reward, next_state, done, self.action_size)
                self.env.add_history(state, action, reward)

                # Perform experience replay if replay memory populated. Note: 10 is an arbitrary constant
                if self.replay_memory.length() > 10 * self.replay_memory.batch_size:
                    self.experience_replay(save_metadata=save_metadata)
                    if save_metadata:
                        save_metadata = False

                state = next_state

            # Save metadat on 100th episode
            if episode == 100:
                self.writer.add_run_metadata(self.run_metadata, 'step' + str(episode))

            # If q_grid not defined yet, and replay memory populated, create q_grid
            if not self.q_grid and self.replay_memory.length() > 1000:
                self.q_grid = self.replay_memory.get_q_grid(1000)
            # Calculate estimated Q value. Note: if q_grid undefined, returns 0
            avg_q = self.estimate_avg_q()

            score = self.test_Q(num_test_episodes=5)
            print("Episode {0}, score {1}".format(episode, score))
            # Save score and average q-values into logs for Tensorboard
            self.writer.add_summary(self.sess.run(self.summary, feed_dict={self.training_score: score, self.avg_q: avg_q}), episode)
            self.episodes_trained += 1

    def test_Q(self, num_test_episodes=10, visualize=False):
        cum_reward = 0
        for episode in range(num_test_episodes):
            done = False
            state = self.env.reset()
            while not done:
                if visualize:
                    self.env.render()
                action = self.get_action(state, epsilon=0)
                next_state, reward, done, _ = self.env.step(action)
                state = next_state
                cum_reward += reward
        return cum_reward / float(num_test_episodes)

    def estimate_avg_q(self):
        if not self.q_grid:
            return 0
        q_avg = 0.0
        num_samples = len(self.q_grid)
        for index in range(num_samples):
            q_avg += np.amax(self.sess.run(self.Q_value, feed_dict={self.state_tf: self.q_grid[index]}))
        return q_avg / num_samples