CREATE DATABASE IF NOT EXISTS flowgen;
USE flowgen;

CREATE TABLE IF NOT EXISTS users (
  id         INT PRIMARY KEY AUTO_INCREMENT,
  username   VARCHAR(64) UNIQUE NOT NULL,
  password   VARCHAR(255) NOT NULL,
  active     TINYINT(1) DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_login DATETIME NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id         BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id    INT NOT NULL,
  jti        VARCHAR(64) UNIQUE NOT NULL,
  issued_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME NOT NULL,
  revoked    TINYINT(1) DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS jobs (
  id           VARCHAR(36) PRIMARY KEY,
  user_id      INT NOT NULL,
  vm_job_id    VARCHAR(36) NULL,
  status       ENUM('pending','running','done','error') DEFAULT 'pending',
  total_images INT DEFAULT 0,
  done_images  INT DEFAULT 0,
  error_msg    TEXT NULL,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
