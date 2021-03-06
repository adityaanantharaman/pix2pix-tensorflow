# -*- coding: utf-8 -*-
"""pix2pix.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1rIBx0Qvwa6GfZRdPeL5b2sAbL1hVUEZV
"""

import tensorflow as tf

import os
import pathlib
import time
import datetime

from matplotlib import pyplot as plt
from IPython import display

dataset_name="facades"

_URL = f'http://efrosgans.eecs.berkeley.edu/pix2pix/datasets/{dataset_name}.tar.gz'

path_to_zip = tf.keras.utils.get_file(
    fname=f"{dataset_name}.tar.gz",
    origin=_URL,
    extract=True)

path_to_zip  = pathlib.Path(path_to_zip)

PATH = path_to_zip.parent/dataset_name

list(PATH.parent.iterdir())

sample_image=tf.io.read_file(str(PATH/'train/1.jpg'))
sample_image=tf.io.decode_jpeg(sample_image)
print(sample_image.shape)

plt.figure()
plt.imshow(sample_image)

def load(image_file):
  img=tf.io.read_file(image_file)
  img=tf.io.decode_jpeg(img)
  w=tf.shape(img)[1]
  w=w//2
  inpimg=img[:,w:,:]
  outimg=img[:,:w,:]
  inpimg=tf.cast(inpimg,tf.float32)
  outimg=tf.cast(outimg,tf.float32)
  return inpimg,outimg

a,b=load(str(PATH/"train/2.jpg"))
plt.figure()
plt.imshow(a/255.0)
plt.figure()
plt.imshow(b/255.0)

BUFFER_SIZE=400
BATCH_SIZE=1
IMGH=256
IMGW=256

def resize(a,b,h,w):
  a=tf.image.resize(a,[h,w],method="nearest")
  b=tf.image.resize(b,[h,w],method="nearest")
  return a,b

def random_crop(a,b):
  stacked=tf.stack([a,b],axis=0)
  cropped=tf.image.random_crop(stacked,[2,IMGH,IMGW,3])
  return cropped[0],cropped[1]

def normalize(a,b):
  a=a/127.5-1.0
  b=b/127.5-1.0
  return a,b

@tf.function()
def random_jitter(inp,real):
  inp,real=resize(inp,real,286,286)
  inp,real=random_crop(inp,real)
  if tf.random.uniform(())>0.5:
    inp=tf.image.flip_left_right(inp)
    real=tf.image.flip_left_right(real)
  return inp,real

plt.figure(figsize=(20,20))
for i in range(0,8,2):
  a,b=load(str(PATH/f'train/{i+1}.jpg'))
  a,b=random_jitter(a,b)
  plt.subplot(4,2,i+1)
  plt.imshow(a/255.0)
  plt.axis('off')
  plt.subplot(4,2,i+2)
  plt.imshow(b/255.0)
  plt.axis('off')
plt.show()

def load_img_train(imfile):
  inp,real=load(imfile)
  inp,real=random_jitter(inp,real)
  inp,real=normalize(inp,real)
  return inp,real

def load_img_test(imfile):
  inp,real=load(imfile)
  inp,real=resize(inp,real,IMGH,IMGW)
  inp,real=normalize(inp,real)
  return inp,real

train_dataset=tf.data.Dataset.list_files(str(PATH/"train/*.jpg"))
train_dataset=train_dataset.map(load_img_train,num_parallel_calls=tf.data.AUTOTUNE)
train_dataset=train_dataset.shuffle(BUFFER_SIZE)
train_dataset=train_dataset.batch(BATCH_SIZE)

try:
  test_dataset=tf.data.Dataset.list_files(str(PATH/"test/*.jpg"))
except:
  test_dataset=tf.data.Dataset.list_files(str(PATH/"val/*.jpg"))
test_dataset=test_dataset.map(load_img_test)
test_dataset=test_dataset.batch(BATCH_SIZE)

OUTPUT_CHANNELS=3

def downsample(filters,size,apply_batchnorm=True):
  initializer=tf.random_normal_initializer(0.,0.02)
  result=tf.keras.Sequential()
  result.add(tf.keras.layers.Conv2D(filters,size,2,"same",
                                    kernel_initializer=initializer,
                                    use_bias=False))
  if apply_batchnorm:
    result.add(tf.keras.layers.BatchNormalization())
  result.add(tf.keras.layers.LeakyReLU())
  return result

def upsample(filters,size,apply_dropout=False):
  initializer=tf.random_normal_initializer(0.,0.02)
  result=tf.keras.Sequential()
  result.add(tf.keras.layers.Conv2DTranspose(filters,size,2,"same",
                                             kernel_initializer=initializer,
                                             use_bias=False))
  result.add(tf.keras.layers.BatchNormalization())
  if apply_dropout:
    result.add(tf.keras.layers.Dropout(0.5))
  result.add(tf.keras.layers.ReLU())
  return result

def Generator():
  inputs=tf.keras.layers.Input(shape=[256,256,3])
  down_stack=[
              downsample(64,4,False),
              downsample(128,4),
              downsample(256,4),
              downsample(512,4),
              downsample(512,4),
              downsample(512,4),
              downsample(512,4),
              downsample(512,4)
  ]
  up_stack=[
            upsample(512,4,True),
            upsample(512,4,True),
            upsample(512,4,True),
            upsample(512,4),
            upsample(256,4),
            upsample(128,4),
            upsample(64,4)
  ]

  initializer=tf.random_normal_initializer(0.,0.02)
  last=tf.keras.layers.Conv2DTranspose(OUTPUT_CHANNELS,4,2,"same",
                                       kernel_initializer=initializer,
                                       activation="tanh")

  x=inputs
  skips=[]
  for down in down_stack:
    x=down(x)
    skips.append(x)
  skips=reversed(skips[:-1])
  for up,skip in zip(up_stack,skips):
    x=up(x)
    x=tf.keras.layers.Concatenate()([x,skip])
  x=last(x)
  return tf.keras.Model(inputs=inputs,outputs=x)

generator=Generator()
tf.keras.utils.plot_model(generator,show_shapes=True,dpi=64)

loss_object=tf.keras.losses.BinaryCrossentropy(from_logits=True)

def generator_loss(disc_generated_output,generated,target):
  gan_loss=loss_object(tf.ones_like(disc_generated_output),disc_generated_output)
  LAMBDA=100
  l1_loss=tf.reduce_mean(tf.abs(generated-target))
  finloss=gan_loss + LAMBDA*l1_loss
  return finloss,gan_loss,l1_loss

def Discriminator():
  initializer=tf.random_normal_initializer(0.,0.02)
  input=tf.keras.layers.Input(shape=[256,256,3])
  target=tf.keras.layers.Input(shape=[256,256,3])
  x=tf.keras.layers.concatenate([input,target])
  x=downsample(64,4,False)(x)
  x=downsample(128,4)(x)
  x=downsample(256,4)(x)
  x=tf.keras.layers.ZeroPadding2D()(x)
  x=tf.keras.layers.Conv2D(512,4,1,kernel_initializer=initializer,use_bias=False)(x)
  x=tf.keras.layers.BatchNormalization()(x)
  x=tf.keras.layers.LeakyReLU()(x)
  x=tf.keras.layers.ZeroPadding2D()(x)
  x=tf.keras.layers.Conv2D(1,4,1,kernel_initializer=initializer)(x)
  return tf.keras.Model(inputs=[input,target],outputs=x)

discriminator=Discriminator()
tf.keras.utils.plot_model(discriminator,show_shapes=True,dpi=64)

loss_object=tf.keras.losses.BinaryCrossentropy(from_logits=True)
def discriminator_loss(disc_generated_output,disc_real_output):
  real_loss=loss_object(tf.ones_like(disc_real_output),disc_real_output)
  gen_loss=loss_object(tf.zeros_like(disc_generated_output),disc_generated_output)
  tot_loss=real_loss+gen_loss
  return tot_loss

generator_optimizer=tf.keras.optimizers.Adam(2e-4,beta_1=0.5)
discriminator_optimizer=tf.keras.optimizers.Adam(2e-4,beta_1=0.5)

checkpoint_dir="./training_checkpoints"
checkpoint_prefix=os.path.join(checkpoint_dir,"ckpt")
checkpoint=tf.train.Checkpoint(generator_optimizer=generator_optimizer,
                               discriminator_optimizer=discriminator_optimizer,
                               generator=generator,
                               discriminator=discriminator)

def generate_images(model,input,target):
  generated=model(input,training=True)
  images=[generated[0],input[0],target[0]]
  plt.figure(figsize=(20,60))
  for i in range(3):
    plt.subplot(1,3,i+1)
    plt.imshow(images[i]*0.5+0.5)
    # plt.axis(emit=False)
  plt.show()

for exinput,extarget in test_dataset.take(1):
  generate_images(generator,exinput,extarget)

log_dir="logs/"

summary_writer = tf.summary.create_file_writer(
  log_dir + "fit/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))

@tf.function
def train_step(input,target,step):
  with tf.GradientTape() as gentape, tf.GradientTape() as distape:
    genimg=generator(input,training=True)

    disgenoutput=discriminator([input,genimg],training=True)
    disrealoutput=discriminator([input,target],training=True)

    genloss,genganloss,genl1loss=generator_loss(disgenoutput,genimg,target)
    disloss=discriminator_loss(disgenoutput,disrealoutput)

  gengrads=gentape.gradient(genloss,generator.trainable_variables)
  disgrads=distape.gradient(disloss,discriminator.trainable_variables)

  generator_optimizer.apply_gradients(zip(gengrads,generator.trainable_variables))
  discriminator_optimizer.apply_gradients(zip(disgrads,discriminator.trainable_variables))

  with summary_writer.as_default():
    tf.summary.scalar('gen_total_loss', genloss, step=step//1000)
    tf.summary.scalar('gen_gan_loss', genganloss, step=step//1000)
    tf.summary.scalar('gen_l1_loss', genl1loss, step=step//1000)
    tf.summary.scalar('disc_loss', disloss, step=step//1000)

def fit(train_ds,test_ds,steps):
  for a,b in test_ds.take(1):
    exinp=a
    extar=b
  start=time.time()
  for step,(inp,tar) in train_ds.repeat().take(steps).enumerate():
    if (step+1)%1000==0:
      display.clear_output(wait=True)
      print(f'Time taken for 1000 steps: {time.time()-start:.2f} sec\n')
      generate_images(generator,exinp,extar)
      print(f"step : {step//1000}")
      start=time.time()
    train_step(inp,tar,step)
    if (step+1)%10==0:
      print('.',end='',flush=True)
    if (step+1)%5000==0:
      checkpoint.save(checkpoint_prefix)

# Commented out IPython magic to ensure Python compatibility.
!pkill 377
# %load_ext tensorboard
# %tensorboard --logdir {log_dir}

fit(train_dataset,test_dataset,40000)

for a,b in test_dataset.take(5):
  generate_images(generator,a,b)

from google.colab import drive
drive.mount("./content/")

# /content/content/MyDrive/pix2pix-weights
# !cp /content/training_checkpoints/ckpt-8.index /content/content/MyDrive/pix2pix-weights

for a,b in test_dataset.take(5):
  generate_images(generator,a,b)

checkpointdir="/content/content/MyDrive/pix2pix-weights/"
checkpoint.restore(tf.train.latest_checkpoint(checkpointdir))

for a,b in test_dataset.take(5):
  generate_images(generator,a,b)

