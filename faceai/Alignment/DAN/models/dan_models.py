#coding=utf-8

import numpy as np
import tensorflow as tf
from ..utils.layers import AffineTransformLayer, TransformParamsLayer, LandmarkImageLayer, LandmarkTransformLayer
from ..utils.utils import bestFit,bestFitRect
from scipy import ndimage

IMGSIZE = 112
N_LANDMARK = 68

def NormRmse(GroudTruth, Prediction):
    Gt = tf.reshape(GroudTruth, [-1, N_LANDMARK, 2])
    Pt = tf.reshape(Prediction, [-1, N_LANDMARK, 2])
    loss = tf.reduce_mean(tf.sqrt(tf.reduce_sum(tf.squared_difference(Gt, Pt), 2)), 1)
    # norm = tf.sqrt(tf.reduce_sum(((tf.reduce_mean(Gt[:, 36:42, :],1) - \
    #     tf.reduce_mean(Gt[:, 42:48, :],1))**2), 1))
    norm = tf.norm(tf.reduce_mean(Gt[:, 36:42, :],1) - tf.reduce_mean(Gt[:, 42:48, :],1), axis=1)
    # cost = tf.reduce_mean(loss / norm)

    return loss/norm



def DAN(MeanShapeNumpy):

    MeanShape = tf.constant(MeanShapeNumpy, dtype=tf.float32)
    InputImage = tf.placeholder(tf.float32,[None, IMGSIZE,IMGSIZE,1])
    GroundTruth = tf.placeholder(tf.float32,[None, N_LANDMARK * 2])
    S1_isTrain = tf.placeholder(tf.bool)
    S2_isTrain = tf.placeholder(tf.bool)
    Ret_dict = {}
    Ret_dict['InputImage'] = InputImage
    Ret_dict['GroundTruth'] = GroundTruth
    Ret_dict['S1_isTrain'] = S1_isTrain
    Ret_dict['S2_isTrain'] = S2_isTrain

    with tf.variable_scope('Stage1'):

        S1_Conv1a = tf.layers.batch_normalization(tf.layers.conv2d(InputImage,64,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Conv1b = tf.layers.batch_normalization(tf.layers.conv2d(S1_Conv1a,64,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Pool1 = tf.layers.max_pooling2d(S1_Conv1b,2,2,padding='same')

        S1_Conv2a = tf.layers.batch_normalization(tf.layers.conv2d(S1_Pool1,128,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Conv2b = tf.layers.batch_normalization(tf.layers.conv2d(S1_Conv2a,128,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Pool2 = tf.layers.max_pooling2d(S1_Conv2b,2,2,padding='same')

        S1_Conv3a = tf.layers.batch_normalization(tf.layers.conv2d(S1_Pool2,256,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Conv3b = tf.layers.batch_normalization(tf.layers.conv2d(S1_Conv3a,256,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Pool3 = tf.layers.max_pooling2d(S1_Conv3b,2,2,padding='same')

        S1_Conv4a = tf.layers.batch_normalization(tf.layers.conv2d(S1_Pool3,512,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Conv4b = tf.layers.batch_normalization(tf.layers.conv2d(S1_Conv4a,512,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain)
        S1_Pool4 = tf.layers.max_pooling2d(S1_Conv4b,2,2,padding='same')

        S1_Pool4_Flat = tf.contrib.layers.flatten(S1_Pool4)
        S1_DropOut = tf.layers.dropout(S1_Pool4_Flat,0.5,training=S1_isTrain)

        S1_Fc1 = tf.layers.batch_normalization(tf.layers.dense(S1_DropOut,256,activation=tf.nn.relu,\
            kernel_initializer=tf.glorot_uniform_initializer()),training=S1_isTrain,name = 'S1_Fc1')
        S1_Fc2 = tf.layers.dense(S1_Fc1,N_LANDMARK * 2)

        S1_Ret = S1_Fc2 + MeanShape
        S1_Cost = tf.reduce_mean(NormRmse(GroundTruth, S1_Ret))

        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS,'Stage1')):
            S1_Optimizer = tf.train.AdamOptimizer(0.001).minimize(S1_Cost,\
                var_list=tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES,"Stage1"))
        
    Ret_dict['S1_Ret'] = S1_Ret
    Ret_dict['S1_Cost'] = S1_Cost
    Ret_dict['S1_Optimizer'] = S1_Optimizer

    with tf.variable_scope('Stage2'):

        S2_AffineParam = TransformParamsLayer(S1_Ret, MeanShape)
        S2_InputImage = AffineTransformLayer(InputImage, S2_AffineParam)
        S2_InputLandmark = LandmarkTransformLayer(S1_Ret, S2_AffineParam)
        S2_InputHeatmap = LandmarkImageLayer(S2_InputLandmark)

        S2_Feature = tf.reshape(tf.layers.dense(S1_Fc1,int((IMGSIZE / 2) * (IMGSIZE / 2)),\
            activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),(-1,int(IMGSIZE / 2),int(IMGSIZE / 2),1))
        S2_FeatureUpScale = tf.image.resize_images(S2_Feature,(IMGSIZE,IMGSIZE),1)

        S2_ConcatInput = tf.layers.batch_normalization(tf.concat([S2_InputImage,S2_InputHeatmap,S2_FeatureUpScale],3),\
            training=S2_isTrain)
        S2_Conv1a = tf.layers.batch_normalization(tf.layers.conv2d(S2_ConcatInput,64,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Conv1b = tf.layers.batch_normalization(tf.layers.conv2d(S2_Conv1a,64,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Pool1 = tf.layers.max_pooling2d(S2_Conv1b,2,2,padding='same')

        S2_Conv2a = tf.layers.batch_normalization(tf.layers.conv2d(S2_Pool1,128,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Conv2b = tf.layers.batch_normalization(tf.layers.conv2d(S2_Conv2a,128,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Pool2 = tf.layers.max_pooling2d(S2_Conv2b,2,2,padding='same')

        S2_Conv3a = tf.layers.batch_normalization(tf.layers.conv2d(S2_Pool2,256,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Conv3b = tf.layers.batch_normalization(tf.layers.conv2d(S2_Conv3a,256,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Pool3 = tf.layers.max_pooling2d(S2_Conv3b,2,2,padding='same')

        S2_Conv4a = tf.layers.batch_normalization(tf.layers.conv2d(S2_Pool3,512,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Conv4b = tf.layers.batch_normalization(tf.layers.conv2d(S2_Conv4a,512,3,1,\
            padding='same',activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Pool4 = tf.layers.max_pooling2d(S2_Conv4b,2,2,padding='same')

        S2_Pool4_Flat = tf.contrib.layers.flatten(S2_Pool4)
        S2_DropOut = tf.layers.dropout(S2_Pool4_Flat,0.5,training=S2_isTrain)

        S2_Fc1 = tf.layers.batch_normalization(tf.layers.dense(S2_DropOut,256,\
            activation=tf.nn.relu,kernel_initializer=tf.glorot_uniform_initializer()),training=S2_isTrain)
        S2_Fc2 = tf.layers.dense(S2_Fc1,N_LANDMARK * 2)

        S2_Ret = LandmarkTransformLayer(S2_Fc2 + S2_InputLandmark,S2_AffineParam, Inverse=True)
        S2_Cost = tf.reduce_mean(NormRmse(GroundTruth,S2_Ret))

        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS,'Stage2')):
            S2_Optimizer = tf.train.AdamOptimizer(0.0001).minimize(S2_Cost,\
                var_list=tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES,"Stage2"))

    Ret_dict['S2_Ret'] = S2_Ret
    Ret_dict['S2_Cost'] = S2_Cost
    Ret_dict['S2_Optimizer'] = S2_Optimizer

    Ret_dict['S2_InputImage'] = S2_InputImage
    Ret_dict['S2_InputLandmark'] = S2_InputLandmark
    Ret_dict['S2_InputHeatmap'] = S2_InputHeatmap
    Ret_dict['S2_FeatureUpScale'] = S2_FeatureUpScale
    
    return Ret_dict

class DANDetector(object):
    def __init__(self,init_inf,model_path):
        self.initLandmarks = init_inf["initLandmarks"].reshape((-1,2))
        self.meanImg = init_inf["meanImg"]
        self.stdDevImg = init_inf["stdDevImg"]
        self.nChannels = 1
        self.imageHeight = IMGSIZE
        self.imageWidth = IMGSIZE

        self.dan = DAN(init_inf["initLandmarks"])
        self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True, gpu_options=tf.GPUOptions(allow_growth=True)))
        saver = tf.train.Saver()
        model_dict = '/'.join(model_path.split('/')[:-1])
        ckpt = tf.train.get_checkpoint_state(model_dict)
        print(model_path)
        readstate = ckpt and ckpt.model_checkpoint_path
        assert readstate, "the params dictionary is not valid"
        print("restore models' param")
        saver.restore(self.sess, model_path)

    def predict(self, databatch):
        s2_landmarks = self.sess.run(self.dan['S2_Ret'],
                                            feed_dict={self.dan['InputImage']:databatch,
                                                       self.dan['S1_isTrain']:False,self.dan['S2_isTrain']:False})
        return s2_landmarks

    def processImg(self,input,recs):
        gray_img = np.mean(input, axis=2).astype(np.uint8)
        initLandmarks_fitrec = bestFitRect(None, self.initLandmarks, recs)
        inputImg, transform = self.CropResizeRotate(gray_img[np.newaxis], initLandmarks_fitrec)

        inputImg = inputImg[:,:,:,np.newaxis]
        inputImg = inputImg - self.meanImg[np.newaxis]
        inputImg = inputImg / self.stdDevImg[np.newaxis]
        output = self.predict(inputImg)

        landmarks = output.reshape((-1, 2))
        return np.dot(landmarks - transform[1], np.linalg.inv(transform[0]))

    def CropResizeRotate(self, img, inputShape):
        A, t = bestFit(self.initLandmarks, inputShape, True)
        A2 = np.linalg.inv(A)
        t2 = np.dot(-t, A2)
        outImg = np.zeros((self.nChannels, self.imageHeight, self.imageWidth), dtype=np.float32)
        for i in range(img.shape[0]):
            outImg[i] = ndimage.interpolation.affine_transform(img[i], A2, t2[[1, 0]],
                                                               output_shape=(self.imageHeight, self.imageWidth))
        return outImg, [A, t]