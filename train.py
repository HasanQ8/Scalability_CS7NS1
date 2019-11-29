#!/usr/bin/env python3
import os
import cv2
import numpy as np
import random
import argparse
import tensorflow as tf
import tensorflow.keras as keras
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)


# Build a Keras model given some parameters
def create_model(captcha_length, captcha_num_symbols, input_shape, model_depth=5, module_size=2):
    input_tensor = keras.Input(input_shape)
    x = input_tensor
    for i, module_length in enumerate([module_size] * model_depth):
        for j in range(module_length):
            x = keras.layers.Conv2D(32 * 2 ** min(i, 3), kernel_size=3, padding='same',
                                    kernel_initializer='he_uniform')(x)
            x = keras.layers.BatchNormalization()(x)
            x = keras.layers.Activation('relu')(x)
        x = keras.layers.MaxPooling2D(2)(x)
    x = keras.layers.Flatten()(x)
    x = [keras.layers.Dense(captcha_num_symbols, activation='softmax',
                            name='char_%d' % (i + 1))(x) for i in range(captcha_length)]
    model = keras.Model(inputs=input_tensor, outputs=x)

    return model


class ImageSequence(keras.utils.Sequence):
    def __init__(self, directory_name, batch_size, captcha_length, captcha_symbols, captcha_width, captcha_height, is_audio):
        self.directory_name = directory_name
        self.batch_size = batch_size
        self.captcha_length = captcha_length
        self.captcha_symbols = captcha_symbols
        self.captcha_width = captcha_width
        self.captcha_height = captcha_height
        self.is_audio = is_audio

        file_list = os.listdir(self.directory_name)
        self.files = dict(zip(map(lambda x: x.split('.')[0], file_list), file_list))
        self.used_files = []
        self.count = len(file_list)

    def __len__(self):
        return int(np.floor(self.count / self.batch_size))

    def __getitem__(self, idx):
        X = np.zeros((self.batch_size, self.captcha_height, self.captcha_width, 3), dtype=np.float32)
        y = [np.zeros((self.batch_size, len(self.captcha_symbols)), dtype=np.uint8)
             for i in range(self.captcha_length)]

        for i in range(self.batch_size):
            random_image_label = random.choice(list(self.files.keys()))
            random_image_file = self.files[random_image_label]

            self.used_files.append(self.files.pop(random_image_label))


            raw_data = cv2.imread(os.path.join(self.directory_name, random_image_file))
            rgb_data = None
            if not self.is_audio:
                # gray scaling the image
                gray_data = cv2.cvtColor(raw_data, cv2.COLOR_BGR2GRAY)
                # applying adaptive threshold
                adaptive = cv2.adaptiveThreshold(gray_data, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 11, 2)

                kernel = np.ones((1, 1), np.uint8)
                # dilating the image
                dilation = cv2.dilate(adaptive, kernel, iterations=1)
                # applying erode
                erosion = cv2.erode(dilation, kernel, iterations=1)
                kernel = np.ones((4, 1), np.uint8)
                dilation = cv2.dilate(erosion, kernel, iterations=1)
                # converting back to RGB format to maintain consistence of image shape
                rgb_data = cv2.cvtColor(dilation, cv2.COLOR_GRAY2RGB)
            else:
                rgb_data = cv2.cvtColor(raw_data, cv2.COLOR_BGR2RGB)

            processed_data = np.array(rgb_data) / 255.0
            X[i] = processed_data

   

            random_image_label = random_image_label.split('_')[0]

            for j, ch in enumerate(random_image_label):
                y[j][i, :] = 0
                y[j][i, self.captcha_symbols.find(ch)] = 1

        return X, y


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--width', help='Width of captcha image', type=int)
    parser.add_argument('--height', help='Height of captcha image', type=int)
    parser.add_argument('--length', help='Length of captchas in characters', type=int)
    parser.add_argument('--batch-size', help='How many images in training captcha batches', type=int)
    parser.add_argument('--train-dataset', help='Where to look for the training image dataset', type=str)
    parser.add_argument('--validate-dataset', help='Where to look for the validation image dataset', type=str)
    parser.add_argument('--output-model-name', help='Where to save the trained model', type=str)
    parser.add_argument('--input-model', help='Where to look for the input model to continue training', type=str)
    parser.add_argument('--epochs', help='How many training epochs to run', type=int)
    parser.add_argument('--symbols', help='File with the symbols to use in captchas', type=str)
    parser.add_argument('--is-audio', help='trains model for audio captcha', type=bool, default=True)
    args = parser.parse_args()

    if args.width is None:
        print("Please specify the captcha image width")
        exit(1)

    if args.height is None:
        print("Please specify the captcha image height")
        exit(1)

    if args.length is None:
        print("Please specify the captcha length")
        exit(1)

    if args.batch_size is None:
        print("Please specify the training batch size")
        exit(1)

    if args.epochs is None:
        print("Please specify the number of training epochs to run")
        exit(1)

    if args.train_dataset is None:
        print("Please specify the path to the training data set")
        exit(1)

    if args.validate_dataset is None:
        print("Please specify the path to the validation data set")
        exit(1)

    if args.output_model_name is None:
        print("Please specify a name for the trained model")
        exit(1)

    if args.symbols is None:
        print("Please specify the captcha symbols file")
        exit(1)

    if args.is_audio is False:
        print("Training model for Image Captcha")
    else:
        print("Training model for Audio Captcha")

    captcha_symbols = None
    with open(args.symbols) as symbols_file:
        captcha_symbols = symbols_file.readline()

    with tf.device('/device:GPU:0'):
        model = create_model(args.length, len(captcha_symbols), (args.height, args.width, 3))

        if args.input_model is not None:
            model.load_weights(args.input_model)

        model.compile(loss='categorical_crossentropy',
                      optimizer=keras.optimizers.Adam(1e-3, amsgrad=True),
                      metrics=['accuracy'])

        model.summary()

        training_data = ImageSequence(args.train_dataset, args.batch_size, args.length, captcha_symbols, args.width,
                                      args.height, args.is_audio)
        validation_data = ImageSequence(args.validate_dataset, args.batch_size, args.length, captcha_symbols,
                                        args.width, args.height, args.is_audio)

        callbacks = [keras.callbacks.EarlyStopping(patience=3),
                     keras.callbacks.ModelCheckpoint(args.output_model_name + '.h5', save_best_only=False)]

        # Save the model architecture to JSON
        with open(args.output_model_name + ".json", "w") as json_file:
            json_file.write(model.to_json())

        try:
            model.fit_generator(generator=training_data,
                                validation_data=validation_data,
                                epochs=args.epochs,
                                callbacks=callbacks,
                                use_multiprocessing=True)
        except KeyboardInterrupt:
            print('KeyboardInterrupt caught, saving current weights as ' + args.output_model_name + '_resume.h5')
            model.save_weights(args.output_model_name + '_resume.h5')


if __name__ == '__main__':
    main()
