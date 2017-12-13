import tensorflow as tf
from tensorflow.contrib.layers.python.layers import initializers

def clipped_error(x):
  # Huber loss
    try:
        return tf.select(tf.abs(x) < 1.0, 0.5 * tf.square(x), tf.abs(x) - 0.5)
    except:
        return tf.where(tf.abs(x) < 1.0, 0.5 * tf.square(x), tf.abs(x) - 0.5)

def conv2d(x,
           output_dim,
           kernel_size,
           stride,
           initializer=tf.contrib.layers.xavier_initializer(),
           activation_fn=tf.nn.relu,
           data_format='NHWC',
           padding='VALID',
           name='conv2d'):
    with tf.variable_scope(name):
        if data_format == 'NCHW':
            stride = [1, 1, stride[0], stride[1]]
            kernel_shape = [kernel_size[0], kernel_size[1], x.get_shape()[1], output_dim]
        elif data_format == 'NHWC':
            stride = [1, stride[0], stride[1], 1]
            kernel_shape = [kernel_size[0], kernel_size[1], x.get_shape()[-1], output_dim]

        w = tf.get_variable('w', kernel_shape, tf.float32, initializer=initializer)
        conv = tf.nn.conv2d(x, w, stride, padding, data_format=data_format)

        # b = tf.get_variable('biases', [output_dim], initializer=tf.constant_initializer(0.0))
        # out = tf.nn.bias_add(conv, b, data_format)
        out = conv

    if activation_fn != None:
        out = activation_fn(out)

    return out, w


def linear(input_, output_size, stddev=0.02, bias_start=0.0, activation_fn=None, name='linear'):
    shape=input_.get_shape().as_list()

    with tf.variable_scope(name):
        w = tf.get_variable('Matrix', [shape[1], output_size], tf.float32,
        tf.random_normal_initializer(stddev = stddev))
        b = tf.get_variable('bias', [output_size],
        initializer=tf.constant_initializer(bias_start))

        out = tf.nn.bias_add(tf.matmul(input_, w), b)

    if activation_fn != None:
        return activation_fn(out), w, b
    else:
        return out, w, b


def elementwise_mat_prod(input_, data_format='NHWC', name='elemnt_wise'):
    shape = input_.get_shape().as_list()
    with tf.variable_scope(name):
        w = tf.get_variable('Matrix', [shape[1], shape[2], 1],
                            tf.float32,
                            tf.constant_initializer(1.0))

        multiplier = tf.tile(w, [1, 1, shape[-1]])

        out = tf.multiply(input_, multiplier)

    return out, w


def weighted_sum(input_, data_format='NDHWC', padding='VALID', name='weighted_sum'):
    shape = input_.get_shape().as_list()
    #tesing: ignore kernel_size and derive it from the input shape

    with tf.variable_scope(name):
        # kernel_shape = [kernel_size[0], kernel_size[1], input_.get_shape()[-1], 1]
        kernel_shape = [shape[1], shape[2], 1, 1, 1]
        stride = [1, 1, 1, 1, 1]
        initializer = tf.constant_initializer(1.0 / (shape[1] * shape[2]))

        input_expanded = tf.expand_dims(input_, axis=-1) # [batch, height,  width, channels, 1]

        w = tf.get_variable('w', kernel_shape, tf.float32, initializer=initializer)
        out = tf.nn.conv3d(input_expanded, w, stride, padding=padding, data_format=data_format)


    return out, w


def depthwise_separable_conv(input_, output_size, is_training, kernel=(3, 3), stride=(1, 1), data_format='NDHWC', padding='VALID', name='weighted_sum'):
    shape = input_.get_shape().as_list()

    with tf.variable_scope(name):
        # kernel_shape = [kernel_size[0], kernel_size[1], input_.get_shape()[-1], 1]
        kernel_shape = [kernel[0], kernel[1], shape[-1], 1]
        stride_shape = [1, stride[0], stride[1], 1]

        initializer = tf.contrib.layers.xavier_initializer()
        filter_dw = tf.get_variable('filter_dw', kernel_shape, tf.float32, initializer=initializer)

        depthwise_conv = tf.nn.depthwise_conv2d(input_, filter_dw, stride_shape, padding=padding)
        batch_norm_1 = tf.layers.batch_normalization(depthwise_conv, training=is_training)
        relu_1 = tf.nn.relu(batch_norm_1)

        pointwise_kernel_shape = [1, 1, shape[-1], output_size]
        pointwise_stride_shape = [1, 1, 1, 1]

        filter_pw = tf.get_variable('filter_pw', pointwise_kernel_shape, tf.float32, initializer=initializer)

        pointwise_conv = tf.nn.conv2d(relu_1, filter_pw, pointwise_stride_shape, padding=padding)
        batch_norm_2 = tf.layers.batch_normalization(pointwise_conv, training=is_training)
        relu_2 = tf.nn.relu(batch_norm_2)
        out = relu_2

    return out, filter_dw, filter_pw

