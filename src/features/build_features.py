import os
import pandas as pd
import numpy as np

from typing import Tuple
from abc import ABC, abstractmethod
from torch.utils.data import Dataset, DataLoader, random_split
from torchmetrics import MeanSquaredError

import pytorch_lightning as pl
import torch

from sklearn.preprocessing import LabelEncoder


#This file contains every common class and function used in this project. 
#It also contains the setup for every dataset used in various recommender system techniques.
#To view the implementation of the corresponding model, check its specific file.

def read_ratings(ratings_csv, data_dir = "data/raw") -> pd.DataFrame :
    '''
    Reads a ratings.csv from the data/raw folder.

    Parameters
    -------
    ratings_csv : str
        The csv file that will be read. Must be corresponding to a rating file.

    Returns
    -------
    pd.DataFrame
        The ratings DataFrame. Its columns are, in order:
        "userId", "movieId", "rating" and "timestamp".
    '''
    data = pd.read_csv(os.path.join(data_dir, ratings_csv))

    temp = pd.DataFrame(LabelEncoder().fit_transform(data["movieId"]))
    data["movieId"] = temp

    data["userId"] -= 1

    print(f"data from read_ratings(): {data.head()}")
    return data

class BaseDataset(Dataset, ABC):
    @abstractmethod
    def split(self, *args, **kwargs) -> Tuple[Dataset, Dataset]:
        '''
        Split the dataset into train split
        and test/validation split

        Returns
        -------
        Tuple[Dataset, Dataset]
            Two Dataset instances for training and validation/testing
        '''

class MovieLens(BaseDataset):
    def __init__(self, ratings_csv, data_dir="data/raw", normalize=False):
        '''
        MovieLens for Matrix Factorization
        Each sample is a tuple of:
        - user_id: int
        - movie_id: int
        - rating: float

        Parameters
        ----------
        data_dir : str, optional
            Path to dataset directory, by default "data/raw"
        normalize : bool, optional
            If True, rating is normalized to (0..1), by default False
        '''
        self.data_dir = data_dir
        self.df = read_ratings(ratings_csv, data_dir)
        # If normalize is True, we'll divide the ratings by 5.0 (max)
        if normalize:
            self.df.rating /= 5.0
        self.num_users = self.df.userId.nunique()
        self.num_movies = self.df.movieId.nunique()
        self.user_id = self.df.userId.values
        self.movie_id = self.df.movieId.values
        self.rating = self.df.rating.values.astype(np.float32)
        self.timestamp = self.df.timestamp

    def __len__(self):
        return len(self.df)
    
    def __getitem__(self, idx):
        return self.user_id[idx], self.movie_id[idx], self.rating[idx]
    
    def split(self, train_ratio = 0.8):
        train_len = int(train_ratio*len(self))
        test_len = len(self) - train_len
        return random_split(self, [train_len, test_len])

class LightDataModule(pl.LightningDataModule):
    """DataModule for PyTorch Lightning.

        Parameters
        ----------
        dataset : BaseML100K
        train_ratio : float, optional
            By default 0.8
        batch_size : int, optional
            By default 32
        num_workers : int, optional
            Number of multi-CPU to fetch data
            By default 2
        prefetch_factor : int, optional
            Number of batches to prefecth, by default 16
        """
    def __init__(self, dataset: BaseDataset,
                 train_ratio=0.8, batch_size=32,
                 num_workers=2, prefetch_factor=16):
        self.dataset = dataset
        self.train_ratio = train_ratio
        self.dataloader_kwargs = {
            "batch_size": batch_size,
            "num_workers": num_workers,
            "prefetch_factor": prefetch_factor,
        }

    def setup(self):
        print("Initiating setup")
        self.num_users = getattr(self.dataset, "num_users", None)
        self.num_movies = getattr(self.dataset, "num_movies", None)
        self.train_split, self.test_split = self.dataset.split(
            self.train_ratio)
        print("Setup has been successfully executed.")

    def train_dataloader(self):
        print("train_dataloader()")
        return DataLoader(self.train_split, **self.dataloader_kwargs, shuffle=True)

    def val_dataloader(self):
        print("val_dataloader()")
        return DataLoader(self.test_split, **self.dataloader_kwargs, shuffle=False)

    def test_dataloader(self):
        print("test_dataloader")
        return DataLoader(self.test_split, **self.dataloader_kwargs, shuffle=False)


class LightModel(pl.LightningModule):
    """Lightning Module to train model"""
    def __init__(self, model_class, lr = 0.001, metrics = MeanSquaredError(), **kwargs):
        super().__init__()
        # We save the hyperparameters for reproducibility
        self.save_hyperparameters()
        self.model = model_class(**kwargs)
        self.sparse = getattr(self.model, "sparse", False)
        self.lr = lr
        self.metrics = metrics

    def configure_optimizers(self):
        if self.sparse:
            return torch.optim.SparseAdam(self.parameters(), self.lr)
        return torch.optim.Adam(self.parameters(), self.lr, weight_decay = 1e-5)
    
    ### The following functions must be implemented specifically.

    def get_loss(self, model_outputs, batch):
        raise NotImplementedError()
    
    def update_metric(self, model_outputs, batch):
        raise NotImplementedError()

    def forward(self, batch):
        raise NotImplementedError()
    
    def _common_step(self, batch, batch_idx):
        model_outputs = self(batch)
        loss = self.get_loss(model_outputs, batch)
        return loss
        #return loss, model_outputs, batch[-1]

    def training_step(self, batch, batch_idx):
        loss = self._common_step(batch, batch_idx)
        return loss
    
    def validation_step(self, batch, batch_idx):
        loss = self._common_step(batch, batch_idx)
        return loss
