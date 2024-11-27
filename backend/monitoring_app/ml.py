import os
import cv2
import torch
import logging
import traceback
import numpy as np
import torch.nn as nn
from threading import Lock
from collections import Counter
from django.conf import settings
from insightface.app import FaceAnalysis
from sklearn.neighbors import NearestNeighbors
from sklearn.model_selection import train_test_split
from rest_framework.exceptions import ValidationError
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import f1_score, precision_score, recall_score
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from monitoring_app import models

# -----------------------------------
# 1. Logging Setup
# -----------------------------------

logger = logging.getLogger("django")


# -----------------------------------
# 2. Global Variables and Device Setup
# -----------------------------------

arcface_model = None

arcface_lock = Lock()


def get_device():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Selected device: {device}")
    return device


def load_arcface_model():
    global arcface_model
    if arcface_model is None:
        with arcface_lock:
            if arcface_model is None:
                device_type = "GPU" if torch.cuda.is_available() else "CPU"
                logger.info(f"Using {device_type} for ArcFace model")
                arcface_model = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                )
                ctx_id = 0 if torch.cuda.is_available() else -1
                arcface_model.prepare(ctx_id=ctx_id, det_size=(640, 640))


# -----------------------------------
# 3. Image Processing Functions
# -----------------------------------


def load_image_from_memory(file):
    """
    Loads an image from memory into a NumPy array.

    Args:
        file (InMemoryUploadedFile): Uploaded image file.

    Returns:
        numpy.ndarray: Image array.

    Raises:
        ValidationError: If the image cannot be read.
    """
    try:
        file_bytes = np.frombuffer(file.read(), np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if image is None:
            raise ValidationError("Невозможно прочитать изображение.")
        return image
    except Exception as e:
        logger.error(f"Ошибка при чтении изображения: {e}")
        raise ValidationError(f"Ошибка чтения изображения: {str(e)}")


def preprocess_image(image):
    """
    Resizes the image if its dimensions are smaller than 640x640.

    Args:
        image (numpy.ndarray): Image array.

    Returns:
        numpy.ndarray: Preprocessed image array.

    Raises:
        ValueError: If the input is not a NumPy array.
    """
    if not isinstance(image, np.ndarray):
        raise ValueError("Expected image as numpy array, got different format.")

    height, width = image.shape[:2]
    if height < 640 or width < 640:
        scale_factor = max(640 / height, 640 / width)
        new_size = (int(width * scale_factor), int(height * scale_factor))
        image = cv2.resize(image, new_size, interpolation=cv2.INTER_CUBIC)
    return image


# -----------------------------------
# 4. Embedding Creation Functions
# -----------------------------------


def create_embeddings_for_staff(staff):
    """
    Creates embeddings for all images (original and augmented) of the staff member.

    Args:
        staff (Staff): Staff object.

    Raises:
        ValueError: If avatar is missing or embeddings cannot be created.
    """
    try:
        if not staff.avatar or not os.path.exists(staff.avatar.path):
            logger.error(f"Avatar отсутствует для {staff.pin}")
            raise ValueError(f"Avatar отсутствует для {staff.pin}")

        avatar_image_path = str(staff.avatar.path)
        augmented_image_dir = str(settings.AUGMENT_ROOT).format(staff_pin=staff.pin)

        if not os.path.exists(augmented_image_dir):
            logger.warning(
                f"Директория аугментации не найдена: {augmented_image_dir}",
            )
            augmented_images = []
        else:
            augmented_images = [
                os.path.join(augmented_image_dir, img)
                for img in os.listdir(augmented_image_dir)
                if img.endswith((".png", ".jpg", ".jpeg"))
            ]

        all_image_paths = [avatar_image_path] + augmented_images

        embeddings = create_embeddings_from_images(all_image_paths)

        if not embeddings:
            logger.error(f"Не удалось создать эмбеддинги для {staff.pin}")
            raise ValueError(f"Не удалось создать эмбеддинги для {staff.pin}")

        embeddings_path = os.path.join(
            os.path.dirname(avatar_image_path), f"{staff.pin}_embeddings.npy"
        )
        np.save(embeddings_path, embeddings)
        logger.info(
            f"Сохранены эмбеддинги для {staff.pin} по пути {embeddings_path}",
        )

    except Exception as e:
        logger.error(
            f"Ошибка при создании эмбеддингов для {staff.pin}: {str(e)}\n{traceback.format_exc()}",
        )
        raise e


def create_embeddings_from_images(image_paths):
    """
    Creates embeddings for a list of image paths.

    Args:
        image_paths (list): List of image file paths.

    Returns:
        list: List of embeddings.
    """
    embeddings = []
    for image_path in image_paths:
        if not os.path.exists(image_path):
            logger.warning(f"Image file does not exist: {image_path}")
            continue

        image = cv2.imread(image_path)
        if image is None:
            logger.warning(f"Failed to load image (possibly corrupted): {image_path}")
            continue

        image = preprocess_image(image)
        embedding = create_face_encoding(image)
        if embedding is not None:
            embeddings.append(embedding)
        else:
            logger.warning(f"Failed to create embedding for image: {image_path}")

    return embeddings


def create_face_encoding(image_or_path):
    """
    Creates a face embedding using the ArcFace model.

    Args:
        image_or_path (numpy.ndarray or str): Image array or image file path.

    Returns:
        list or None: Face embedding or None if failed.
    """
    try:
        load_arcface_model()
        if isinstance(image_or_path, str):
            if not os.path.exists(image_or_path):
                logger.warning(f"Image file not found: {image_or_path}")
                return None

            image = cv2.imread(image_or_path)
            if image is None:
                logger.warning(f"Failed to load image: {image_or_path}")
                return None

            image = preprocess_image(image)
        else:
            if not isinstance(image_or_path, np.ndarray):
                logger.warning("Invalid image format, expected numpy array.")
                return None
            image = image_or_path

        faces = arcface_model.get(image)
        if not faces:
            logger.warning(f"No face detected in image {str(image_or_path)}")
            return None

        return faces[0].embedding.tolist()

    except Exception as e:
        logger.error(f"Ошибка при создании encoding: {e}")
        return None


# -----------------------------------
# 5. Negative Sample Generation
# -----------------------------------


def generate_negative_samples(staff, neighbors_count=7):
    """
    Generates negative samples for training the face recognition model.

    Args:
        staff (Staff): Staff object.
        neighbors_count (int): Number of negative samples to generate.

    Returns:
        list: List of negative embeddings.
    """
    logger.info(f"Generating negative samples for {staff.pin}")

    staff_list = list(
        models.Staff.objects.filter(avatar__isnull=False).exclude(id=staff.id)
    )
    negative_embeddings = []

    for neighbor in staff_list:
        try:
            embeddings_path = os.path.join(
                os.path.dirname(neighbor.avatar.path), f"{neighbor.pin}_embeddings.npy"
            )
            if os.path.exists(embeddings_path):
                embeddings = np.load(embeddings_path)
                negative_embeddings.extend(embeddings)
            else:
                image_path = neighbor.avatar.path
                if not os.path.exists(image_path):
                    continue

                image = cv2.imread(image_path)
                if image is None:
                    logger.error(f"Failed to load image: {image_path}")
                    continue

                image = preprocess_image(image)

                encoding = create_face_encoding(image)
                if encoding is not None:
                    negative_embeddings.append(encoding)

        except Exception as e:
            logger.warning(
                f"Failed to create encoding for negative sample from {neighbor.pin}: {e}",
            )

        if len(negative_embeddings) >= neighbors_count:
            break

    return negative_embeddings[:neighbors_count]


# -----------------------------------
# 6. Face Recognition Models
# -----------------------------------


class GeneralFaceRecognitionModel(nn.Module):
    """
    General face recognition model using MLP for all staff members.

    Args:
        num_classes (int): Number of classes (staff members).
    """

    def __init__(self, num_classes):
        super(GeneralFaceRecognitionModel, self).__init__()
        self.fc1 = nn.Linear(512, 512)
        self.bn1 = nn.BatchNorm1d(512)
        self.dropout1 = nn.Dropout(0.5)
        self.fc2 = nn.Linear(512, 256)
        self.bn2 = nn.BatchNorm1d(256)
        self.dropout2 = nn.Dropout(0.5)
        self.fc3 = nn.Linear(256, num_classes)

    def forward(self, x):
        x = torch.relu(self.bn1(self.fc1(x)))
        x = self.dropout1(x)
        x = torch.relu(self.bn2(self.fc2(x)))
        x = self.dropout2(x)
        return self.fc3(x)


class FaceRecognitionResNet(nn.Module):
    """
    Individual face recognition model using MLP.

    Args:
        pretrained (bool): Whether to use pretrained weights.
    """

    def __init__(self, pretrained=False):
        super(FaceRecognitionResNet, self).__init__()
        self.fc1 = nn.Linear(512, 512)
        self.bn1 = nn.BatchNorm1d(512)
        self.dropout1 = nn.Dropout(0.5)
        self.fc2 = nn.Linear(512, 256)
        self.bn2 = nn.BatchNorm1d(256)
        self.dropout2 = nn.Dropout(0.5)
        self.fc3 = nn.Linear(256, 128)
        self.bn3 = nn.BatchNorm1d(128)
        self.dropout3 = nn.Dropout(0.5)
        self.fc4 = nn.Linear(128, 1)

    def forward(self, x):
        x = torch.relu(self.bn1(self.fc1(x)))
        x = self.dropout1(x)
        x = torch.relu(self.bn2(self.fc2(x)))
        x = self.dropout2(x)
        x = torch.relu(self.bn3(self.fc3(x)))
        x = self.dropout3(x)
        return self.fc4(x)


# -----------------------------------
# 7. Evaluation Metrics
# -----------------------------------


def evaluate_metrics(y_true, y_pred):
    """
    Computes Precision, Recall, and F1-score.

    Args:
        y_true (list or np.ndarray): True labels.
        y_pred (list or np.ndarray): Predicted labels.

    Returns:
        tuple: Precision, Recall, F1-score.
    """
    precision = precision_score(y_true, y_pred, average="weighted", zero_division=0)
    recall = recall_score(y_true, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)
    return precision, recall, f1


# -----------------------------------
# 8. Class Weights and Sampler
# -----------------------------------


def get_class_weights(labels, class_weights):
    """
    Assigns weight to each sample based on its class.

    Args:
        labels (list or np.ndarray): List of class labels (integers).
        class_weights (np.ndarray): Array of class weights corresponding to each class.

    Returns:
        WeightedRandomSampler: Sampler for balancing classes.
    """
    samples_weights = class_weights[labels]
    samples_weights = torch.from_numpy(samples_weights).double()
    sampler = WeightedRandomSampler(
        samples_weights, num_samples=len(samples_weights), replacement=True
    )
    return sampler


# -----------------------------------
# 9. Model Saving and Loading
# -----------------------------------


def save_model_for_staff(model, staff, model_path_suffix="model.pt"):
    """
    Saves the trained model for a staff member.

    Args:
        model (nn.Module): Trained model.
        staff (Staff): Staff object.
        model_path_suffix (str): Suffix for the model file name.

    Raises:
        Exception: If saving fails.
    """

    try:
        model_path = os.path.join(
            os.path.dirname(staff.avatar.path), f"{staff.pin}_{model_path_suffix}"
        )
        torch.save(model.state_dict(), model_path)
        logger.info(f"Model for {staff.pin} saved at {model_path}")

    except Exception as e:
        logger.error(f"Error saving model for {staff.pin}: {str(e)}")
        raise e


def load_model_for_staff(staff, model_path_suffix="model.pt"):
    """
    Loads the trained model for a staff member.

    Args:
        staff (Staff): Staff object.
        model_path_suffix (str): Suffix for the model file name.

    Returns:
        nn.Module: Loaded model.

    Raises:
        ValueError: If the model file does not exist.
    """

    model_path = os.path.join(
        os.path.dirname(staff.avatar.path), f"{staff.pin}_{model_path_suffix}"
    )
    if not os.path.exists(model_path):
        logger.error(f"Модель для {staff.pin} не найдена")
        raise ValueError(f"Модель для {staff.pin} не найдена")

    device = get_device()
    model = FaceRecognitionResNet(pretrained=False).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    logger.info(f"Model for {staff.pin} loaded from {model_path}")
    return model


def load_general_model():
    """
    Loads the trained general face recognition model.

    Returns:
        nn.Module: Loaded general model.

    Raises:
        ValueError: If the general model file does not exist.
    """

    model_path = os.path.join(
        settings.GENERAL_MODELS_ROOT, "general_face_recognition_model.pt"
    )
    if not os.path.exists(model_path):
        logger.error("Общая модель не найдена")
        raise ValueError("Общая модель не найдена")

    device = get_device()
    num_classes = len(models.Staff.objects.filter(avatar__isnull=False))
    model = GeneralFaceRecognitionModel(num_classes=num_classes).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    logger.info(f"General model loaded from {model_path}")
    return model


# -----------------------------------
# 10. Model Training Functions
# -----------------------------------


def train_face_recognition_model(staff, epochs=20, batch_size=256, learning_rate=1e-4):
    """
    Trains an individual face recognition model for the given staff member.

    Args:
        staff (Staff): Staff object.
        epochs (int): Number of training epochs.
        batch_size (int): Batch size.
        learning_rate (float): Learning rate.

    Returns:
        FaceRecognitionResNet: Trained model.
    """
    logger.info("Начало обучения индивидуальной модели.")

    device = get_device()

    if not staff.avatar or not os.path.exists(staff.avatar.path):
        logger.error(f"Avatar отсутствует для {staff.pin}")
        raise ValueError(f"Avatar отсутствует для {staff.pin}")

    embeddings_path = os.path.join(
        os.path.dirname(staff.avatar.path), f"{staff.pin}_embeddings.npy"
    )
    if not os.path.exists(embeddings_path):
        logger.info(f"Эмбеддинги не найдены для {staff.pin}, создаем их.")
        create_embeddings_for_staff(staff)

    if not os.path.exists(embeddings_path):
        logger.error(f"Эмбеддинги для {staff.pin} не найдены по пути {embeddings_path}")
        raise ValueError(
            f"Эмбеддинги для {staff.pin} не найдены по пути {embeddings_path}"
        )

    positive_embeddings = np.load(embeddings_path)
    if positive_embeddings.size == 0:
        logger.error(f"Эмбеддинги пусты для {staff.pin}")
        raise ValueError(f"Эмбеддинги пусты для {staff.pin}")

    positive_embeddings = torch.tensor(positive_embeddings, dtype=torch.float32).to(
        device
    )

    negative_embeddings = generate_negative_samples(staff)

    if positive_embeddings.size(0) == 0 or len(negative_embeddings) == 0:
        logger.error(f"Недостаточно данных для обучения модели для {staff.pin}.")
        raise ValueError(f"Недостаточно данных для обучения модели для {staff.pin}.")

    negative_embeddings = torch.tensor(negative_embeddings, dtype=torch.float32).to(
        device
    )

    embeddings_combined = torch.cat([positive_embeddings, negative_embeddings], dim=0)
    labels = torch.tensor(
        [1] * positive_embeddings.size(0) + [0] * negative_embeddings.size(0),
        dtype=torch.float32,
    ).to(device)

    labels_np = labels.cpu().numpy()
    labels_int = labels_np.astype(int)

    classes = np.unique(labels_np)
    if len(classes) < 2:
        logger.warning(f"Only one class found for {staff.pin}. Adjusting classes.")
        classes = np.append(classes, 1 - classes[0])

    class_weights = 1.0 / np.array([np.sum(labels_np == c) for c in classes])

    sampler = get_class_weights(labels_int, class_weights)

    dataset = TensorDataset(embeddings_combined, labels)
    train_loader = DataLoader(
        dataset, batch_size=batch_size, sampler=sampler, num_workers=0
    )

    inputs_train, inputs_val, labels_train, labels_val = train_test_split(
        embeddings_combined.cpu().numpy(),
        labels.cpu().numpy(),
        test_size=0.2,
        random_state=42,
        stratify=labels.cpu().numpy(),
    )

    inputs_val = torch.tensor(inputs_val, dtype=torch.float32).to(device)
    labels_val = torch.tensor(labels_val, dtype=torch.float32).to(device)

    val_dataset = TensorDataset(inputs_val, labels_val)
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    model = FaceRecognitionResNet(pretrained=False).to(device)

    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=1e-4
    )
    scaler = torch.GradScaler("cuda")

    best_f1 = 0
    patience = 5
    trigger_times = 0

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        all_preds = []
        all_labels_list = []

        for batch_inputs, batch_labels in train_loader:
            batch_inputs = batch_inputs.to(device)
            batch_labels = batch_labels.to(device)

            optimizer.zero_grad()
            with torch.autocast("cuda"):
                outputs = model(batch_inputs).squeeze()
                loss = criterion(outputs, batch_labels)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item()

            preds = torch.sigmoid(outputs) >= 0.5
            all_preds.extend(preds.cpu().numpy())
            all_labels_list.extend(batch_labels.cpu().numpy())

        train_accuracy = np.mean(np.array(all_preds) == np.array(all_labels_list))
        train_precision, train_recall, train_f1 = evaluate_metrics(
            all_labels_list, all_preds
        )
        logger.info(
            f"Epoch {epoch+1}, Train Loss: {train_loss / len(train_loader):.4f}, "
            f"Train Acc: {train_accuracy:.4f}, Precision: {train_precision:.4f}, "
            f"Recall: {train_recall:.4f}, F1: {train_f1:.4f}"
        )

        model.eval()
        val_loss = 0.0
        val_preds = []
        val_true = []

        with torch.no_grad():
            for batch_inputs, batch_labels in val_loader:
                batch_inputs = batch_inputs.to(device)
                batch_labels = batch_labels.to(device)

                outputs = model(batch_inputs).squeeze()
                loss = criterion(outputs, batch_labels)
                val_loss += loss.item()

                preds = torch.sigmoid(outputs) >= 0.5
                val_preds.extend(preds.cpu().numpy())
                val_true.extend(batch_labels.cpu().numpy())

        val_accuracy = np.mean(np.array(val_preds) == np.array(val_true))
        val_precision, val_recall, val_f1 = evaluate_metrics(val_true, val_preds)
        logger.info(
            f"Epoch {epoch+1}, Validation Loss: {val_loss / len(val_loader):.4f}, "
            f"Val Acc: {val_accuracy:.4f}, Precision: {val_precision:.4f}, "
            f"Recall: {val_recall:.4f}, F1: {val_f1:.4f}"
        )

        if val_f1 > best_f1:
            best_f1 = val_f1
            trigger_times = 0
            best_model_path = os.path.join(
                os.path.dirname(staff.avatar.path), f"{staff.pin}_best_model.pt"
            )
            os.makedirs(os.path.dirname(best_model_path), exist_ok=True)
            torch.save(model.state_dict(), best_model_path)
            logger.info(f"Best model updated and saved at {best_model_path}")
        else:
            trigger_times += 1
            if trigger_times >= patience:
                logger.info("Early stopping triggered.")
                break

    final_model_path = os.path.join(
        os.path.dirname(staff.avatar.path), f"{staff.pin}_model.pt"
    )
    os.makedirs(os.path.dirname(final_model_path), exist_ok=True)
    torch.save(model.state_dict(), final_model_path)
    logger.info(f"Model for {staff.pin} saved at {final_model_path}")

    return model


def train_general_model(epochs=100, batch_size=256, learning_rate=1e-4):
    """
    Trains a general face recognition model using data from all staff members.

    Args:
        epochs (int): Number of training epochs.
        batch_size (int): Batch size.
        learning_rate (float): Learning rate.

    Raises:
        ValueError: If insufficient data is available for training.
    """
    logger.info("Начало обучения общей модели.")

    device = get_device()

    staff_members = list(models.Staff.objects.filter(avatar__isnull=False).distinct())
    num_staff = len(staff_members)
    logger.info(f"Number of staff members (avatar__isnull=False): {num_staff}")

    if num_staff == 0:
        logger.error("No staff members found with avatars for training.")
        raise ValueError("No staff members found with avatars for training.")

    all_embeddings = []
    all_labels = []
    staff_pin_to_label = {staff.pin: idx for idx, staff in enumerate(staff_members)}

    for staff in staff_members:
        if (
            not staff.avatar
            or not staff.avatar.path
            or not os.path.exists(staff.avatar.path)
        ):
            logger.warning(
                f"Staff {staff.pin} has no associated avatar file. Skipping."
            )
            continue

        embeddings_path = os.path.join(
            os.path.dirname(staff.avatar.path), f"{staff.pin}_embeddings.npy"
        )
        if not os.path.exists(embeddings_path):
            logger.warning(
                f"Embeddings for {staff.pin} not found at {embeddings_path}. Skipping."
            )
            continue

        embeddings = np.load(embeddings_path)
        if embeddings.size == 0:
            logger.warning(f"Embeddings for {staff.pin} are empty. Skipping.")
            continue

        labels = [staff_pin_to_label[staff.pin]] * len(embeddings)
        all_embeddings.extend(embeddings)
        all_labels.extend(labels)

    all_embeddings = np.array(all_embeddings)
    all_labels = np.array(all_labels)

    label_counts = Counter(all_labels)
    logger.info(f"Label counts before filtering: {label_counts}")

    valid_labels = [label for label, count in label_counts.items() if count >= 2]
    logger.info(f"Valid labels (>=2 samples): {valid_labels}")

    if not valid_labels:
        logger.error("No classes with at least two samples available for training.")
        raise ValueError("Insufficient data: No classes with at least two samples.")

    mask = np.isin(all_labels, valid_labels)
    all_embeddings = all_embeddings[mask]
    all_labels = all_labels[mask]

    excluded_labels = set(range(num_staff)) - set(valid_labels)
    if excluded_labels:
        logger.warning(f"Excluded classes with insufficient samples: {excluded_labels}")

    num_classes = len(staff_pin_to_label)
    logger.info(f"Number of classes after filtering: {num_classes}")

    if not all_embeddings.any():
        logger.error("Insufficient data to train the general model after filtering.")
        raise ValueError(
            "Insufficient data to train the general model after filtering."
        )

    all_embeddings = torch.tensor(all_embeddings, dtype=torch.float32).to(device)
    all_labels = torch.tensor(all_labels, dtype=torch.long).to(device)

    if torch.any(all_labels >= num_classes) or torch.any(all_labels < 0):
        invalid_labels = all_labels[(all_labels >= num_classes) | (all_labels < 0)]
        logger.error(f"Invalid labels found: {invalid_labels}")
        raise ValueError("Found labels outside the valid range.")

    logger.info("All labels are within the valid range.")

    unique_y = np.unique(all_labels.cpu().numpy())

    class_weights_present = compute_class_weight(
        class_weight="balanced",
        classes=unique_y,
        y=all_labels.cpu().numpy(),
    )

    class_weights = np.ones(num_classes, dtype=np.float32)

    class_weights[unique_y] = class_weights_present

    class_weights = torch.tensor(class_weights, dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    try:
        inputs_train, inputs_val, labels_train, labels_val = train_test_split(
            all_embeddings.cpu().numpy(),
            all_labels.cpu().numpy(),
            test_size=0.2,
            random_state=42,
            stratify=all_labels.cpu().numpy(),
        )
    except ValueError as e:
        logger.error(f"Error during train_test_split: {e}")
        raise

    inputs_train = torch.tensor(inputs_train, dtype=torch.float32).to(device)
    inputs_val = torch.tensor(inputs_val, dtype=torch.float32).to(device)
    labels_train = torch.tensor(labels_train, dtype=torch.long).to(device)
    labels_val = torch.tensor(labels_val, dtype=torch.long).to(device)

    labels_train_np = labels_train.cpu().numpy()
    labels_train_int = labels_train_np.astype(int)

    sampler = get_class_weights(labels_train_int, class_weights.cpu().numpy())

    train_dataset = TensorDataset(inputs_train, labels_train)
    val_dataset = TensorDataset(inputs_val, labels_val)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, sampler=sampler, num_workers=0
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    model = GeneralFaceRecognitionModel(num_classes=num_staff).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=1e-4
    )
    scaler = torch.GradScaler("cuda")

    best_f1 = 0
    patience = 5
    trigger_times = 0

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        all_preds = []
        all_labels_list = []

        for batch_inputs, batch_labels in train_loader:
            batch_inputs = batch_inputs.to(device)
            batch_labels = batch_labels.to(device)

            optimizer.zero_grad()
            with torch.autocast("cuda"):
                outputs = model(batch_inputs)
                loss = criterion(outputs, batch_labels)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item()

            preds = torch.argmax(outputs, dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels_list.extend(batch_labels.cpu().numpy())

        train_accuracy = np.mean(np.array(all_preds) == np.array(all_labels_list))
        train_precision, train_recall, train_f1 = evaluate_metrics(
            all_labels_list, all_preds
        )
        logger.info(
            f"Epoch {epoch+1}, Train Loss: {train_loss / len(train_loader):.4f}, "
            f"Train Acc: {train_accuracy:.4f}, Precision: {train_precision:.4f}, "
            f"Recall: {train_recall:.4f}, F1: {train_f1:.4f}"
        )

        model.eval()
        val_loss = 0.0
        val_preds = []
        val_true = []

        with torch.no_grad():
            for batch_inputs, batch_labels in val_loader:
                batch_inputs = batch_inputs.to(device)
                batch_labels = batch_labels.to(device)

                outputs = model(batch_inputs)
                loss = criterion(outputs, batch_labels)
                val_loss += loss.item()

                preds = torch.argmax(outputs, dim=1)
                val_preds.extend(preds.cpu().numpy())
                val_true.extend(batch_labels.cpu().numpy())

        val_accuracy = np.mean(np.array(val_preds) == np.array(val_true))
        val_precision, val_recall, val_f1 = evaluate_metrics(val_true, val_preds)
        logger.info(
            f"Epoch {epoch+1}, Validation Loss: {val_loss / len(val_loader):.4f}, "
            f"Val Acc: {val_accuracy:.4f}, Precision: {val_precision:.4f}, "
            f"Recall: {val_recall:.4f}, F1: {val_f1:.4f}"
        )

        if val_f1 > best_f1:
            best_f1 = val_f1
            trigger_times = 0
            best_model_path = os.path.join(
                settings.GENERAL_MODELS_ROOT, "best_general_face_recognition_model.pt"
            )
            os.makedirs(os.path.dirname(best_model_path), exist_ok=True)
            torch.save(model.state_dict(), best_model_path)
            logger.info(f"Best model updated and saved at {best_model_path}")
        else:
            trigger_times += 1
            if trigger_times >= patience:
                logger.info("Early stopping triggered.")
                break

    final_model_path = os.path.join(
        settings.GENERAL_MODELS_ROOT, "general_face_recognition_model.pt"
    )
    os.makedirs(os.path.dirname(final_model_path), exist_ok=True)

    torch.save(model.state_dict(), final_model_path)
    logger.info(f"General model saved at {final_model_path}")


# -----------------------------------
# 11. Face Recognition Function
# -----------------------------------


def recognize_faces_in_image(image_file):
    """
    Recognizes faces in an image and identifies staff members.

    Args:
        image_file (InMemoryUploadedFile): Uploaded image file.

    Returns:
        tuple: (recognized_staff, unknown_faces)

    Raises:
        ValidationError: If recognition fails.
    """
    try:
        load_arcface_model()
        img = load_image_from_memory(image_file)
        faces = arcface_model.get(img)

        if not faces:
            logger.warning("Лица не найдены на изображении")
            raise ValidationError("Лица не найдены на изображении")

        embeddings = [face.embedding for face in faces]
        embeddings = np.array(embeddings)
        embeddings_normalized = embeddings / np.linalg.norm(
            embeddings, axis=1, keepdims=True
        )

        # Загрузка эмбеддингов сотрудников
        staff_members = list(models.Staff.objects.filter(face_mask__isnull=False))
        staff_embeddings = np.array(
            [staff.face_mask.mask_encoding for staff in staff_members]
        )
        staff_embeddings_normalized = staff_embeddings / np.linalg.norm(
            staff_embeddings, axis=1, keepdims=True
        )

        # Инициализация NearestNeighbors для косинусного сходства
        nbrs = NearestNeighbors(n_neighbors=1, metric="cosine").fit(
            staff_embeddings_normalized
        )

        # Поиск ближайшего соседа для каждого лица
        distances, indices = nbrs.kneighbors(embeddings_normalized)

        recognized_staff = []
        unknown_faces = []

        for idx, (distance, staff_idx) in enumerate(zip(distances, indices)):
            bbox = faces[idx].bbox.astype(int).tolist()
            similarity = 1 - distance[0]  # Косинусное сходство

            if similarity > settings.FACE_RECOGNITION_THRESHOLD:
                staff = staff_members[staff_idx[0]]
                recognized_staff.append(
                    {
                        "pin": staff.pin,
                        "name": staff.name,
                        "surname": staff.surname,
                        "department": (
                            staff.department.name if staff.department else None
                        ),
                        "similarity": similarity,
                        "bbox": bbox,
                    }
                )
            else:
                unknown_faces.append(
                    {
                        "status": "unknown",
                        "bbox": bbox,
                    }
                )

        logger.info(
            f"Recognition completed. Recognized: {len(recognized_staff)}, Unknown: {len(unknown_faces)}"
        )
        return recognized_staff, unknown_faces

    except Exception as e:
        logger.error(f"Ошибка при распознавании лиц: {str(e)}")
        raise ValidationError(f"Ошибка при распознавании лиц: {str(e)}")
