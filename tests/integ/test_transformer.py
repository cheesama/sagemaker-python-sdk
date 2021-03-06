# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
from __future__ import absolute_import

import gzip
import os
import pickle
import sys

import pytest

from sagemaker import KMeans
from sagemaker.mxnet import MXNet
from sagemaker.transformer import Transformer
from tests.integ import DATA_DIR, TRAINING_DEFAULT_TIMEOUT_MINUTES
from tests.integ.timeout import timeout


@pytest.mark.continuous_testing
def test_transform_mxnet(sagemaker_session):
    data_path = os.path.join(DATA_DIR, 'mxnet_mnist')
    script_path = os.path.join(data_path, 'mnist.py')

    mx = MXNet(entry_point=script_path, role='SageMakerRole', train_instance_count=1,
               train_instance_type='ml.c4.xlarge', sagemaker_session=sagemaker_session)

    train_input = mx.sagemaker_session.upload_data(path=os.path.join(data_path, 'train'),
                                                   key_prefix='integ-test-data/mxnet_mnist/train')
    test_input = mx.sagemaker_session.upload_data(path=os.path.join(data_path, 'test'),
                                                  key_prefix='integ-test-data/mxnet_mnist/test')

    with timeout(minutes=TRAINING_DEFAULT_TIMEOUT_MINUTES):
        mx.fit({'train': train_input, 'test': test_input})

    transform_input_path = os.path.join(data_path, 'transform', 'data.csv')
    transform_input_key_prefix = 'integ-test-data/mxnet_mnist/transform'
    transform_input = mx.sagemaker_session.upload_data(path=transform_input_path,
                                                       key_prefix=transform_input_key_prefix)

    transformer = _create_transformer_and_transform_job(mx, transform_input)
    transformer.wait()


@pytest.mark.continuous_testing
def test_attach_transform_kmeans(sagemaker_session):
    data_path = os.path.join(DATA_DIR, 'one_p_mnist')
    pickle_args = {} if sys.version_info.major == 2 else {'encoding': 'latin1'}

    # Load the data into memory as numpy arrays
    train_set_path = os.path.join(data_path, 'mnist.pkl.gz')
    with gzip.open(train_set_path, 'rb') as f:
        train_set, _, _ = pickle.load(f, **pickle_args)

    kmeans = KMeans(role='SageMakerRole', train_instance_count=1,
                    train_instance_type='ml.c4.xlarge', k=10, sagemaker_session=sagemaker_session,
                    output_path='s3://{}/'.format(sagemaker_session.default_bucket()))

    # set kmeans specific hp
    kmeans.init_method = 'random'
    kmeans.max_iterators = 1
    kmeans.tol = 1
    kmeans.num_trials = 1
    kmeans.local_init_method = 'kmeans++'
    kmeans.half_life_time_size = 1
    kmeans.epochs = 1

    records = kmeans.record_set(train_set[0][:100])
    with timeout(minutes=TRAINING_DEFAULT_TIMEOUT_MINUTES):
        kmeans.fit(records)

    transform_input_path = os.path.join(data_path, 'transform_input.csv')
    transform_input_key_prefix = 'integ-test-data/one_p_mnist/transform'
    transform_input = kmeans.sagemaker_session.upload_data(path=transform_input_path,
                                                           key_prefix=transform_input_key_prefix)

    transformer = _create_transformer_and_transform_job(kmeans, transform_input)

    attached_transformer = Transformer.attach(transformer.latest_transform_job.name,
                                              sagemaker_session=sagemaker_session)
    attached_transformer.wait()


def _create_transformer_and_transform_job(estimator, transform_input):
    transformer = estimator.transformer(1, 'ml.m4.xlarge')
    transformer.transform(transform_input, content_type='text/csv')
    return transformer
