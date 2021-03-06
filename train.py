# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
r"""Simple speech recognition to spot a limited number of keywords.

This is a self-contained example script that will train a very basic audio
recognition model in TensorFlow. It downloads the necessary training data and
runs with reasonable defaults to train within a few hours even only using a CPU.
For more information, please see
https://www.tensorflow.org/tutorials/audio_recognition.

It is intended as an introduction to using neural networks for audio
recognition, and is not a full speech recognition system. For more advanced
speech systems, I recommend looking into Kaldi. This network uses a keyword
detection style to spot discrete words from a small vocabulary, consisting of
"yes", "no", "up", "down", "left", "right", "on", "off", "stop", and "go".

To run the training process, use:

bazel run tensorflow/examples/speech_commands:train

This will write out checkpoints to /tmp/speech_commands_train/, and will
download over 1GB of open source training data, so you'll need enough free space
and a good internet connection. The default data is a collection of thousands of
one-second .wav files, each containing one spoken word. This data set is
collected from https://aiyprojects.withgoogle.com/open_speech_recording, please
consider contributing to help improve this and other models!

As training progresses, it will print out its accuracy metrics, which should
rise above 90% by the end. Once it's complete, you can run the freeze script to
get a binary GraphDef that you can easily deploy on mobile applications.

If you want to train on your own data, you'll need to create .wavs with your
recordings, all at a consistent length, and then arrange them into subfolders
organized by label. For example, here's a possible file structure:

my_wavs >
  up >
    audio_0.wav
    audio_1.wav
  down >
    audio_2.wav
    audio_3.wav
  other>
    audio_4.wav
    audio_5.wav

You'll also need to tell the script what labels to look for, using the
`--wanted_words` argument. In this case, 'up,down' might be what you want, and
the audio in the 'other' folder would be used to train an 'unknown' category.

To pull this all together, you'd run:

bazel run tensorflow/examples/speech_commands:train -- \
--data_dir=my_wavs --wanted_words=up,down

"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import os.path
import sys

import numpy as np
import pandas as pd
from six.moves import xrange  # pylint: disable=redefined-builtin
import tensorflow as tf

#import input_data
from input_data import *
from models import *
from tensorflow.python.platform import gfile

FLAGS = None

def load_labels(filename):
  """Read in labels, one label per line."""
  return [line.rstrip() for line in tf.gfile.GFile(filename)]

def main(_):
  # We want to see all the logging messages for this tutorial.
  tf.logging.set_verbosity(tf.logging.INFO)

  # Start a new TensorFlow session.
  sess = tf.InteractiveSession()

  # Begin by making sure we have the training data we need. If you already have
  # training data of your own, use `--data_url= ` on the command line to avoid
  # downloading.

  model_settings = prepare_model_settings(FLAGS.arch_config_file)
  audio_processor = AudioProcessor(FLAGS.data_url, FLAGS.data_dir, model_settings)
  model_settings['noise_label_count'] = audio_processor.background_label_count() + 1

  graph = Graph(model_settings)

  time_shift_samples = int((model_settings['time_shift_ms'] * model_settings['sample_rate']) / 1000)
  # Figure out the learning rates for each training phase. Since it's often
  # effective to have high learning rates at the start of training, followed by
  # lower levels towards the end, the number of steps and learning rates can be
  # specified as comma-separated lists to define the rate at each stage. For
  # example --how_many_training_steps=10000,3000 --learning_rate=0.001,0.0001
  # will run 13,000 training loops in total, with a rate of 0.001 for the first
  # 10,000, and 0.0001 for the final 3,000.
  training_steps_list = model_settings['how_many_training_steps']
  learning_rates_list = model_settings['learning_rate']
  if len(training_steps_list) != len(learning_rates_list):
    raise Exception(
        '--how_many_training_steps and --learning_rate must be equal length '
        'lists, but are %d and %d long instead' % (len(training_steps_list),
                                                   len(learning_rates_list)))

  tf.summary.scalar('accuracy', graph.evaluation_step)

  global_step = tf.contrib.framework.get_or_create_global_step()
  increment_global_step = tf.assign(global_step, global_step + 1)

  saver = tf.train.Saver()

  # Merge all the summaries and write them out to /tmp/retrain_logs (by default)
  merged_summaries = tf.summary.merge_all()
  train_writer = tf.summary.FileWriter(FLAGS.summaries_dir + '/train',
                                       sess.graph)
  validation_writer = tf.summary.FileWriter(FLAGS.summaries_dir + '/validation')

  tf.global_variables_initializer().run()

  start_step = 1

  if FLAGS.start_checkpoint:
    graph.load_variables_from_checkpoint(sess, FLAGS.start_checkpoint)
    start_step = global_step.eval(session=sess)

  tf.logging.info('Training from step: %d ', start_step)

  # Save graph.pbtxt.
  tf.train.write_graph(sess.graph_def, FLAGS.checkpoint_dir,
                       graph.get_arch_name() + '.pbtxt')

  # Save list of words.
  with gfile.GFile(
      os.path.join(FLAGS.checkpoint_dir, graph.get_arch_name() + '_labels.txt'),
      'w') as f:
    f.write('\n'.join(audio_processor.words_list))

  batch_size = int(model_settings['batch_size'])

  # Training loop.
  training_steps_max = np.sum(training_steps_list)
  for training_step in xrange(start_step, training_steps_max + 1):
    # Figure out what the current learning rate is.
    training_steps_sum = 0
    for i in range(len(training_steps_list)):
      training_steps_sum += training_steps_list[i]
      if training_step <= training_steps_sum:
        learning_rate_value = learning_rates_list[i]
        break
    # Pull the audio samples we'll use for training.
    train_fingerprints, train_ground_truth, train_noise_labels, _ = audio_processor.get_data(
        batch_size, 0, model_settings, model_settings['background_frequency'],
        model_settings['background_volume'], time_shift_samples, 'training', sess, features=model_settings['features'])
    # Run the graph with this batch of training data.
    train_summary, train_accuracy, cross_entropy_value, _, _ = sess.run(
        [
            merged_summaries, graph.evaluation_step, graph.cross_entropy_mean, graph.train_step,
            increment_global_step
        ],
        feed_dict={
            graph.fingerprint_input: train_fingerprints,
            graph.ground_truth_input: train_ground_truth,
            graph.learning_rate_input: learning_rate_value,
            graph.is_training: 1,
            graph.dropout_prob: 0.5
        })

    tf.logging.info('Main Step #%d: rate %f, accuracy %.1f%%, cross entropy %f' %
                    (training_step, learning_rate_value, train_accuracy * 100,
                     cross_entropy_value))

    if graph.is_adversarial():
        adv_train_accuracy, adv_cross_entropy_value, _ = sess.run(
            [
                graph.adv_evaluation_step, graph.adv_cross_entropy_mean, graph.adv_train_step
            ],
            feed_dict={
                graph.fingerprint_input: train_fingerprints,
                graph.noise_labels: train_noise_labels,
                graph.adv_learning_rate_input: learning_rate_value,
                graph.is_training: 1,
                graph.dropout_prob: 0.5
            })
        tf.logging.info('Adversarial Step #%d: rate %f, accuracy %.1f%%, cross entropy %f' %
                    (training_step, learning_rate_value, adv_train_accuracy * 100,
                     adv_cross_entropy_value))

    train_writer.add_summary(train_summary, training_step)

    is_last_step = (training_step == training_steps_max)
    if (training_step % model_settings['eval_step_interval']) == 0 or is_last_step:
      set_size = audio_processor.set_size('validation')
      total_accuracy = 0
      total_conf_matrix = None
      for i in xrange(0, set_size, batch_size):
        validation_fingerprints, validation_ground_truth, noise_labels, _ = (
            audio_processor.get_data(batch_size, i, model_settings, 0.0,
                                     0.0, 0, 'validation', sess, features=model_settings['features']))
        # Run a validation step and capture training summaries for TensorBoard
        # with the `merged` op.
        validation_summary, validation_accuracy, conf_matrix = sess.run(
            [merged_summaries, graph.evaluation_step, graph.confusion_matrix],
            feed_dict={
                graph.fingerprint_input: validation_fingerprints,
                graph.ground_truth_input: validation_ground_truth,
                graph.is_training: 0,
                graph.dropout_prob: 1.0
            })
        validation_writer.add_summary(validation_summary, training_step)
        bs = min(batch_size, set_size - i)
        total_accuracy += (validation_accuracy * bs) / set_size
        if total_conf_matrix is None:
          total_conf_matrix = conf_matrix
        else:
          total_conf_matrix += conf_matrix
      tf.logging.info('Confusion Matrix:\n %s' % (total_conf_matrix))
      tf.logging.info('Step %d: Validation accuracy = %.1f%% (N=%d)' %
                      (training_step, total_accuracy * 100, set_size))

    # Save the model checkpoint periodically.
    if (training_step % model_settings['save_step_interval'] == 0 or
        training_step == training_steps_max):
      checkpoint_path = os.path.join(FLAGS.checkpoint_dir,
                                     graph.get_arch_name() + '.ckpt')
      tf.logging.info('Saving to "%s-%d"', checkpoint_path, training_step)
      saver.save(sess, checkpoint_path, global_step=training_step)


  # Evaluation metric
  true_positives = np.diag(total_conf_matrix)
  false_positives = np.sum(total_conf_matrix, axis=0) - true_positives
  false_negatives = np.sum(total_conf_matrix, axis=1) - true_positives
  precision = (true_positives / (true_positives + false_positives)).squeeze()
  recall = (true_positives / (true_positives + false_negatives)).squeeze()
  F1_score = (2 * (precision * recall) / (precision + recall)).squeeze()
  final_statistics = np.stack([precision, recall, F1_score], axis=1)
  path_to_labels = model_settings['path_to_labels']
  labels = load_labels(path_to_labels)
  stat_df = pd.DataFrame(final_statistics, index=labels, columns=['precision', 'recall', 'F1_score'])
  stat_df.to_csv(model_settings['arch'] + '_metric.csv', index=True, header=True, sep='\t')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--data_url',
        type=str,
        default='http://download.tensorflow.org/data/speech_commands_v0.01.tar.gz',
        help='Location of speech training data archive on the web.')
    parser.add_argument(
        '--data_dir',
        type=str,
        default='/home/vitaly/competition/train/audio/',
        help="""\
        Where to download the speech training data to.
        """)

    parser.add_argument(
        '--summaries_dir',
        type=str,
        default='/tmp/retrain_logs',
        help='Where to save summary logs for TensorBoard.')

    parser.add_argument(
        '--checkpoint_dir',
        type=str,
        default='/tmp/speech_commands_train',
        help='Directory to write event logs and checkpoint.')

    parser.add_argument(
        '--start_checkpoint',
        type=str,
        default='',
        help='If specified, restore this pretrained model before any training.')

    parser.add_argument(
        '--arch_config_file',
        type=str,
        default='model_configs/dummy_conf',
        help='File containing model parameters')
    parser.add_argument(
        '--check_nans',
        type=bool,
        default=False,
        help='Whether to check for invalid numbers during processing')

    FLAGS, unparsed = parser.parse_known_args()
    tf.app.run(main=main, argv=[sys.argv[0]] + unparsed)
