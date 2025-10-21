CREATE TABLE user_status (
  status_id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(50) NOT NULL
);

INSERT INTO user_status (status_id, name) VALUES
(1, 'active'),
(2, 'pending'),
(3, 'rejected'),
(4, 'blocked');




ALTER TABLE users
ADD CONSTRAINT fk_users_status
FOREIGN KEY (status) REFERENCES user_status(status_id);




DELIMITER $$

CREATE TRIGGER set_default_status
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    IF NEW.role_id = 2 THEN
        SET NEW.status = 1; -- Buyer = Active
    ELSEIF NEW.role_id = 3 OR NEW.role_id = 4 THEN
        SET NEW.status = 2; -- Seller or Rider = Pending
    ELSE
        SET NEW.status = 1; -- Admin or any other role = Active
    END IF;
END$$

DELIMITER ;





UPDATE users
SET status = CASE
    WHEN role_id = 2 THEN 1
    WHEN role_id IN (3, 4) THEN 2
    ELSE 1
END;
