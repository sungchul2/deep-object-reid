# Copyright (C) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

import logging
import os
import os.path as osp
from collections import (namedtuple,
                        OrderedDict)
from copy import deepcopy
from pprint import pformat
from typing import Any, Callable, Dict, List, Optional, Type

import pytest
from ote_sdk.entities.subset import Subset
from ote_sdk.entities.model_template import parse_model_template
from ote_sdk.entities.model import ModelEntity
from ote_sdk.configuration.helper import create as ote_sdk_configuration_helper_create

from torchreid.integration.sc.utils import (ClassificationDatasetAdapter,
                                            generate_label_schema)

from ote_sdk.test_suite.training_test_case import (OTETestCaseInterface,
                                                   generate_ote_integration_test_case_class)
from ote_sdk.test_suite.e2e_test_system import DataCollector, e2e_pytest_performance
from ote_sdk.test_suite.training_tests_common import (make_path_be_abs,
                                                      make_paths_be_abs,
                                                      KEEP_CONFIG_FIELD_VALUE,
                                                      REALLIFE_USECASE_CONSTANT,
                                                      ROOT_PATH_KEY)
from ote_sdk.test_suite.training_tests_helper import (OTETestHelper,
                                                      DefaultOTETestCreationParametersInterface,
                                                      OTETrainingTestInterface)
from ote_sdk.test_suite.training_tests_actions import (OTETestTrainingAction,
                                                       BaseOTETestAction,
                                                       OTETestTrainingEvaluationAction,
                                                       OTETestExportAction,
                                                       OTETestExportEvaluationAction,
                                                       OTETestPotAction,
                                                       OTETestPotEvaluationAction,
                                                       OTETestNNCFAction,
                                                       OTETestNNCFEvaluationAction,
                                                       OTETestNNCFExportAction,
                                                       OTETestNNCFExportEvaluationAction,
                                                       OTETestNNCFGraphAction,
                                                       create_environment_and_task)


logger = logging.getLogger(__name__)

def DATASET_PARAMETERS_FIELDS() -> List[str]:
    return deepcopy(['annotations_train',
                     'images_train_dir',
                     'annotations_val',
                     'images_val_dir',
                     'annotations_test',
                     'images_test_dir',
                     ])

DatasetParameters = namedtuple('DatasetParameters', DATASET_PARAMETERS_FIELDS())


def _get_dataset_params_from_dataset_definitions(dataset_definitions, dataset_name):
    if dataset_name not in dataset_definitions:
        raise ValueError(f'dataset {dataset_name} is absent in dataset_definitions, '
                         f'dataset_definitions.keys={list(dataset_definitions.keys())}')
    cur_dataset_definition = dataset_definitions[dataset_name]
    training_parameters_fields = {k: v for k, v in cur_dataset_definition.items()
                                  if k in DATASET_PARAMETERS_FIELDS()}
    make_paths_be_abs(training_parameters_fields, dataset_definitions[ROOT_PATH_KEY])

    assert set(DATASET_PARAMETERS_FIELDS()) == set(training_parameters_fields.keys()), \
            f'ERROR: dataset definitions for name={dataset_name} does not contain all required fields'
    assert all(training_parameters_fields.values()), \
            f'ERROR: dataset definitions for name={dataset_name} contains empty values for some required fields'

    params = DatasetParameters(**training_parameters_fields)
    return params

def _create_classification_dataset_and_labels_schema(dataset_params):
    logger.debug(f'Using for train annotation file {dataset_params.annotations_train}')
    logger.debug(f'Using for val annotation file {dataset_params.annotations_val}')
    dataset = ClassificationDatasetAdapter(
        train_data_root=osp.join(dataset_params.images_train_dir),
        train_ann_file=osp.join(dataset_params.annotations_train),
        val_data_root=osp.join(dataset_params.images_val_dir),
        val_ann_file=osp.join(dataset_params.annotations_val),
        test_data_root=osp.join(dataset_params.images_test_dir),
        test_ann_file=osp.join(dataset_params.annotations_test))
    labels_schema = generate_label_schema(dataset.get_labels(), dataset.is_multilabel())
    return dataset, labels_schema


class ClassificationTestNNCFGraphAction(OTETestNNCFGraphAction):

    def _get_compressed_model(self, task):
        # pylint:disable=protected-access
        from torchreid.integration.nncf.compression import wrap_nncf_model

        # Disable quantaizers initialization
        for compression in task._cfg["nncf_config"]['compression']:
            if compression["algorithm"] == "quantization":
                compression["initializer"] = {
                    "batchnorm_adaptation": {
                        "num_bn_adaptation_samples": 0
                    }
                }

        _, compressed_model, _ = wrap_nncf_model(task._model, task._cfg)
        return compressed_model


def get_image_classification_test_action_classes() -> List[Type[BaseOTETestAction]]:
    return [
        ClassificationTestTrainingAction,
        OTETestTrainingEvaluationAction,
        OTETestExportAction,
        OTETestExportEvaluationAction,
        OTETestPotAction,
        OTETestPotEvaluationAction,
        OTETestNNCFAction,
        OTETestNNCFEvaluationAction,
        OTETestNNCFExportAction,
        OTETestNNCFExportEvaluationAction,
        ClassificationTestNNCFGraphAction
    ]

class ClassificationTrainingTestParameters(DefaultOTETestCreationParametersInterface):
    def test_case_class(self) -> Type[OTETestCaseInterface]:
        return generate_ote_integration_test_case_class(
            get_image_classification_test_action_classes()
        )

    def test_bunches(self) -> List[Dict[str, Any]]:
        test_bunches = [
                dict(
                    model_name=[
                       'Custom_Image_Classification_EfficinetNet-B0',
                       'Custom_Image_Classification_MobileNet-V3-large-1x',
                    ],
                    dataset_name='lg_chem_short',
                    usecase='precommit',
                ),
                dict(
                    model_name=[
                       'Custom_Image_Classification_EfficinetNet-B0',
                       'Custom_Image_Classification_MobileNet-V3-large-1x',
                    ],
                    dataset_name=['lg_chem','cifar100'],
                    max_num_epochs=KEEP_CONFIG_FIELD_VALUE,
                    batch_size=KEEP_CONFIG_FIELD_VALUE,
                    usecase=REALLIFE_USECASE_CONSTANT,
                ),
        ]
        return deepcopy(test_bunches)

    def short_test_parameters_names_for_generating_id(self) -> OrderedDict:
        DEFAULT_SHORT_TEST_PARAMETERS_NAMES_FOR_GENERATING_ID = OrderedDict(
            [
                ("test_stage", "ACTION"),
                ("model_name", "model"),
                ("dataset_name", "dataset"),
                ("max_num_epochs", "num_epochs"),
                ("batch_size", "batch"),
                ("usecase", "usecase"),
            ]
        )
        return deepcopy(DEFAULT_SHORT_TEST_PARAMETERS_NAMES_FOR_GENERATING_ID)

    def test_parameters_defining_test_case_behavior(self) -> List[str]:
        DEFAULT_TEST_PARAMETERS_DEFINING_IMPL_BEHAVIOR = [
            "model_name",
            "dataset_name",
            "max_num_epochs",
            "batch_size",
        ]
        return deepcopy(DEFAULT_TEST_PARAMETERS_DEFINING_IMPL_BEHAVIOR)

    def default_test_parameters(self) -> Dict[str, Any]:
        DEFAULT_TEST_PARAMETERS = {
            "max_num_epochs": 1,
            "batch_size": 2,
        }
        return deepcopy(DEFAULT_TEST_PARAMETERS)

# TODO: This function copies with minor change OTETestTrainingAction
#             from ote_sdk.test_suite.
#             Try to avoid copying of code.
class ClassificationTestTrainingAction(OTETestTrainingAction):
    _name = "training"

    def __init__(
        self, dataset, labels_schema, template_path, max_num_epochs, batch_size
    ):
        self.dataset = dataset
        self.labels_schema = labels_schema
        self.template_path = template_path
        self.num_training_iters = max_num_epochs
        self.batch_size = batch_size

    def _run_ote_training(self, data_collector):
        logger.debug(f"self.template_path = {self.template_path}")

        print(f"train dataset: {len(self.dataset.get_subset(Subset.TRAINING))} items")
        print(
            f"validation dataset: "
            f"{len(self.dataset.get_subset(Subset.VALIDATION))} items"
        )

        logger.debug("Load model template")
        self.model_template = parse_model_template(self.template_path)

        logger.debug("Set hyperparameters")
        params = ote_sdk_configuration_helper_create(
            self.model_template.hyper_parameters.data
        )
        if self.num_training_iters != KEEP_CONFIG_FIELD_VALUE:
            params.learning_parameters.max_num_epochs = int(self.num_training_iters)
            logger.debug(
                f"Set params.learning_parameters.max_num_epochs="
                f"{params.learning_parameters.max_num_epochs}"
            )
        else:
            logger.debug(
                f"Keep params.learning_parameters.max_num_epochs="
                f"{params.learning_parameters.max_num_epochs}"
            )

        if self.batch_size != KEEP_CONFIG_FIELD_VALUE:
            params.learning_parameters.batch_size = int(self.batch_size)
            logger.debug(
                f"Set params.learning_parameters.batch_size="
                f"{params.learning_parameters.batch_size}"
            )
        else:
            logger.debug(
                f"Keep params.learning_parameters.batch_size="
                f"{params.learning_parameters.batch_size}"
            )

        logger.debug("Setup environment")
        self.environment, self.task = create_environment_and_task(
            params, self.labels_schema, self.model_template
        )

        logger.debug("Train model")
        self.output_model = ModelEntity(
            self.dataset,
            self.environment.get_model_configuration()
        )

        self.copy_hyperparams = deepcopy(self.task._hyperparams)

        self.task.train(self.dataset, self.output_model)

        score_name, score_value = self._get_training_performance_as_score_name_value()
        logger.info(f"performance={self.output_model.performance}")
        data_collector.log_final_metric("metric_name", self.name + "/" + score_name)
        data_collector.log_final_metric("metric_value", score_value)


class TestOTEReallifeClassification(OTETrainingTestInterface):
    """
    The main class of running test in this file.
    """
    PERFORMANCE_RESULTS = None # it is required for e2e system
    helper = OTETestHelper(ClassificationTrainingTestParameters())

    @classmethod
    def get_list_of_tests(cls, usecase: Optional[str] = None):
        """
        This method should be a classmethod. It is called before fixture initialization, during
        tests discovering.
        """
        return cls.helper.get_list_of_tests(usecase)

    @pytest.fixture
    def params_factories_for_test_actions_fx(self, current_test_parameters_fx,
                                             dataset_definitions_fx, template_paths_fx,
                                             ote_current_reference_dir_fx) -> Dict[str,Callable[[], Dict]]:
        logger.debug('params_factories_for_test_actions_fx: begin')

        test_parameters = deepcopy(current_test_parameters_fx)
        dataset_definitions = deepcopy(dataset_definitions_fx)
        template_paths = deepcopy(template_paths_fx)
        def _training_params_factory() -> Dict:
            if dataset_definitions is None:
                pytest.skip('The parameter "--dataset-definitions" is not set')

            model_name = test_parameters['model_name']
            dataset_name = test_parameters['dataset_name']
            max_num_epochs = test_parameters['max_num_epochs']
            batch_size = test_parameters['batch_size']

            dataset_params = _get_dataset_params_from_dataset_definitions(dataset_definitions, dataset_name)

            if model_name not in template_paths:
                raise ValueError(f'Model {model_name} is absent in template_paths, '
                                 f'template_paths.keys={list(template_paths.keys())}')
            template_path = make_path_be_abs(template_paths[model_name], template_paths[ROOT_PATH_KEY])

            logger.debug('training params factory: Before creating dataset and labels_schema')
            dataset, labels_schema = _create_classification_dataset_and_labels_schema(dataset_params)
            logger.debug('training params factory: After creating dataset and labels_schema')

            return {
                'dataset': dataset,
                'labels_schema': labels_schema,
                'template_path': template_path,
                'max_num_epochs': max_num_epochs,
                'batch_size': batch_size,
            }

        def _nncf_graph_params_factory() -> Dict:
            if dataset_definitions is None:
                pytest.skip('The parameter "--dataset-definitions" is not set')

            model_name = test_parameters['model_name']
            dataset_name = test_parameters['dataset_name']

            dataset_params = _get_dataset_params_from_dataset_definitions(dataset_definitions, dataset_name)

            if model_name not in template_paths:
                raise ValueError(f'Model {model_name} is absent in template_paths, '
                                 f'template_paths.keys={list(template_paths.keys())}')
            template_path = make_path_be_abs(template_paths[model_name], template_paths[ROOT_PATH_KEY])

            logger.debug('training params factory: Before creating dataset and labels_schema')
            dataset, labels_schema = _create_classification_dataset_and_labels_schema(dataset_params)
            logger.debug('training params factory: After creating dataset and labels_schema')

            return {
                'dataset': dataset,
                'labels_schema': labels_schema,
                'template_path': template_path,
                'reference_dir': ote_current_reference_dir_fx,
            }

        params_factories_for_test_actions = {
            'training': _training_params_factory,
            'nncf_graph': _nncf_graph_params_factory,
        }
        logger.debug('params_factories_for_test_actions_fx: end')
        return params_factories_for_test_actions

    @pytest.fixture
    def test_case_fx(self, current_test_parameters_fx, params_factories_for_test_actions_fx):
        """
        This fixture returns the test case class OTEIntegrationTestCase that should be used for the current test.
        Note that the cache from the test helper allows to store the instance of the class
        between the tests.
        If the main parameters used for this test are the same as the main parameters used for the previous test,
        the instance of the test case class will be kept and re-used. It is helpful for tests that can
        re-use the result of operations (model training, model optimization, etc) made for the previous tests,
        if these operations are time-consuming.
        If the main parameters used for this test differs w.r.t. the previous test, a new instance of
        test case class will be created.
        """
        test_case = type(self).helper.get_test_case(current_test_parameters_fx,
                                                    params_factories_for_test_actions_fx)
        return test_case

    # TODO(lbeynens): move to common fixtures
    @pytest.fixture
    def data_collector_fx(self, request) -> DataCollector:
        setup = deepcopy(request.node.callspec.params)
        setup['environment_name'] = os.environ.get('TT_ENVIRONMENT_NAME', 'no-env')
        setup['test_type'] = os.environ.get('TT_TEST_TYPE', 'no-test-type') # TODO: get from e2e test type
        setup['scenario'] = 'api' # TODO(lbeynens): get from a fixture!
        setup['test'] = request.node.name
        setup['subject'] = 'deep-object-reid'
        setup['project'] = 'ote'
        if 'test_parameters' in setup:
            assert isinstance(setup['test_parameters'], dict)
            if 'dataset_name' not in setup:
                setup['dataset_name'] = setup['test_parameters'].get('dataset_name')
            if 'model_name' not in setup:
                setup['model_name'] = setup['test_parameters'].get('model_name')
            if 'test_stage' not in setup:
                setup['test_stage'] = setup['test_parameters'].get('test_stage')
            if 'usecase' not in setup:
                setup['usecase'] = setup['test_parameters'].get('usecase')
        logger.info(f'creating DataCollector: setup=\n{pformat(setup, width=140)}')
        data_collector = DataCollector(name='TestOTEIntegration',
                                       setup=setup)
        with data_collector:
            logger.info('data_collector is created')
            yield data_collector
        logger.info('data_collector is released')

    @e2e_pytest_performance
    def test(self,
             test_parameters,
             test_case_fx, data_collector_fx,
             cur_test_expected_metrics_callback_fx):
        # TODO(pfinashx): remove after fixing loading aux weights in NNCF
        if "MobileNet" in test_parameters["model_name"] and (
                "nncf" in test_parameters["test_stage"]
                or "nncf_graph" in test_parameters["test_stage"]
        ):
            pytest.xfail("The MobileNet model requires loading aux weights for NNCF")
        test_case_fx.run_stage(test_parameters['test_stage'], data_collector_fx,
                               cur_test_expected_metrics_callback_fx)
