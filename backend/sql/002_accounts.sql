USE skillproof;

-- One account owns one profile. Evidence and quiz history already reference that profile,
-- so foreign-key cascades isolate all durable student data by account.
CREATE TABLE IF NOT EXISTS user_accounts (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  email VARCHAR(254) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  profile_id BIGINT UNSIGNED NOT NULL UNIQUE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE
) ENGINE=InnoDB;
