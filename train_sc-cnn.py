# -*- coding: utf-8 -*-

import sys
import six
import argparse
import numpy as np
from sklearn.cross_validation import train_test_split

import chainer
import chainer.links as L
from chainer import optimizers, cuda, serializers
import chainer.functions as F

from CNNSC import CNNSC
import util

"""
Code for the paper Convolutional Neural Networks for Sentence Classification (EMNLP2014)

CNNによるテキスト分類 (posi-nega)
 - 単語ベクトルにはWordEmbeddingモデルを使用
"""

#引数の設定
parser = argparse.ArgumentParser()
parser.add_argument('--gpu  '    , dest='gpu'        , type=int, default=0,            help='1: use gpu, 0: use cpu')
parser.add_argument('--data '    , dest='data'       , type=str, default='input.dat',  help='an input data file')
parser.add_argument('--epoch'    , dest='epoch'      , type=int, default=100,          help='number of epochs to learn')
parser.add_argument('--batchsize', dest='batchsize'  , type=int, default=50,           help='learning minibatch size')

args = parser.parse_args()
batchsize   = args.batchsize    # minibatch size
n_epoch     = args.epoch        # エポック数(パラメータ更新回数)

# Prepare dataset
dataset, height, width = util.load_data(args.data)

print 'height (max length of sentences):', height
print 'width (size of wordembedding vecteor ):', width

dataset['source'] = dataset['source'].astype(np.float32) #特徴量
dataset['target'] = dataset['target'].astype(np.int32) #ラベル

x_train, x_test, y_train, y_test = train_test_split(dataset['source'], dataset['target'], test_size=0.10)
N_test = y_test.size         # test data size
N = len(x_train)             # train data size
in_units = x_train.shape[1]  # 入力層のユニット数 (語彙数)

# (nsample, channel, height, width) の4次元テンソルに変換
input_channel = 1
x_train = x_train.reshape(len(x_train), input_channel, height, width) 
x_test  = x_test.reshape(len(x_test), input_channel, height, width)

#"""
# 隠れ層のユニット数)
n_units = 100
n_label = 2
filter_height = 3
filter_width  = width
output_channel = 100
pooling_size = 2
max_sentence_len = height

print output_channel * int(max_sentence_len / pooling_size)

model = L.Classifier(CNNSC(input_channel, output_channel, filter_height, filter_width, n_units, n_label, max_sentence_len))

# Setup optimizer
optimizer = optimizers.AdaDelta()
optimizer.setup(model)
optimizer.add_hook(chainer.optimizer.GradientClipping(3))

#GPUを使うかどうか
if args.gpu > 0:
    cuda.check_cuda_available()
    cuda.get_device(args.gpu).use()
    model.to_gpu()
xp = np if args.gpu <= 0 else cuda.cupy #args.gpu <= 0: use cpu, otherwise: use gpu

# Learning loop
for epoch in six.moves.range(1, n_epoch + 1):

    print 'epoch', epoch, '/', n_epoch
    
    # training
    perm = np.random.permutation(N) #ランダムな整数列リストを取得
    sum_train_loss     = 0.0
    sum_train_accuracy = 0.0
    for i in six.moves.range(0, N, batchsize):

        #perm を使い x_train, y_trainからデータセットを選択 (毎回対象となるデータは異なる)
        x = chainer.Variable(xp.asarray(x_train[perm[i:i + batchsize]])) #source
        t = chainer.Variable(xp.asarray(y_train[perm[i:i + batchsize]])) #target
        
        model.zerograds()
        loss = model(x, t) # 損失の計算

        sum_train_loss += loss.data * len(t)
        sum_train_accuracy += model.accuracy.data * len(t)

        # 最適化を実行
        loss.backward()
        optimizer.update()

    print('train mean loss={}, accuracy={}'.format(sum_train_loss / N, sum_train_accuracy / N)) #平均誤差

    # evaluation
    sum_test_loss     = 0.0
    sum_test_accuracy = 0.0
    for i in six.moves.range(0, N_test, batchsize):

        # all test data
        x = chainer.Variable(xp.asarray(x_test[i:i + batchsize]))
        t = chainer.Variable(xp.asarray(y_test[i:i + batchsize]))
        
        loss = model(x, t) # 損失の計算
        sum_test_loss += loss.data * len(t)
        sum_test_accuracy += model.accuracy.data * len(t)

    print(' test mean loss={}, accuracy={}'.format(sum_test_loss / N_test, sum_test_accuracy / N_test)) #平均誤差

    sys.stdout.flush()

#modelとoptimizerを保存
print 'save the model'
serializers.save_npz('sc_cnn.model', model)
print 'save the optimizer'
serializers.save_npz('sc_cnn.state', optimizer)

