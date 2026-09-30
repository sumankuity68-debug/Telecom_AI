from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Customer
from backend.schemas import UserRegister, UserLogin, Token, UserOut, OtpSendRequest, OtpVerifyRequest
from backend.auth import hash_password, verify_password, create_access_token
from backend.dependencies import get_current_user
from backend.rate_limiter import limiter, LOGIN_RATE_LIMIT, OTP_RATE_LIMIT
from authy import normalize_phone, send_verification_otp, verify_otp

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user account with hashed password and link to a customer record.
    """
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already registered",
        )

    # Clean phone number if provided
    phone = normalize_phone(user_data.phone) if user_data.phone else None

    # Check if customer exists by customer_id or phone, or create new customer
    customer = None
    if user_data.customer_id:
        customer = db.query(Customer).filter(Customer.customer_id == user_data.customer_id.upper()).first()

    if not customer and phone:
        customer = db.query(Customer).filter(Customer.phone == phone).first()

    if not customer and user_data.name and phone:
        # Create new Customer record
        count = db.query(Customer).count() + 1
        new_customer_id = f"CUST{count:03d}"
        customer = Customer(
            customer_id=new_customer_id,
            name=user_data.name.strip(),
            phone=phone,
            email=user_data.email or f"{user_data.username}@example.com",
            location=user_data.location or "Kolkata",
            customer_type=user_data.customer_type or "individual",
            account_status="active",
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)

    customer_id = customer.customer_id if customer else (user_data.customer_id.upper() if user_data.customer_id else None)

    # Hash password securely
    hashed_pw = hash_password(user_data.password)

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        phone=phone,
        hashed_password=hashed_pw,
        customer_id=customer_id,
        is_active=True,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Issue JWT token
    token = create_access_token({
        "sub": new_user.username,
        "customer_id": customer_id,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "customer_id": customer_id,
        "username": new_user.username,
    }


@router.post("/login", response_model=Token)
@limiter.limit(LOGIN_RATE_LIMIT)
def login(request: Request, credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate user via username or mobile number and issue JWT token.
    """
    identifier = credentials.username.strip()

    # Find user by username or phone
    user = (
        db.query(User)
        .filter((User.username == identifier) | (User.phone == identifier))
        .first()
    )

    # If user record not found in users table, check if customer exists by phone
    # and auto-provision user account for backward compatibility with demo accounts
    if not user:
        clean_phone = normalize_phone(identifier)
        customer = (
            db.query(Customer)
            .filter((Customer.phone == clean_phone) | (Customer.customer_id == identifier.upper()))
            .first()
        )
        if customer and verify_password(credentials.password, hash_password("123456")):
            # Create user on the fly for existing customer
            user = User(
                username=customer.customer_id.lower(),
                email=customer.email,
                phone=customer.phone,
                hashed_password=hash_password(credentials.password),
                customer_id=customer.customer_id,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Issue JWT token
    token = create_access_token({
        "sub": user.username,
        "customer_id": user.customer_id,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "customer_id": user.customer_id,
        "username": user.username,
    }


@router.get("/me", response_model=UserOut)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Retrieve authenticated user profile using Bearer JWT token.
    """
    return current_user


@router.post("/otp/send")
@limiter.limit(OTP_RATE_LIMIT)
def request_otp(request: Request, data: OtpSendRequest, db: Session = Depends(get_db)):
    """
    Dispatch real SMS OTP via Twilio Verify to user's mobile number.
    """
    phone = normalize_phone(data.phone)
    if len(phone) != 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid 10-digit mobile number.",
        )
    success, message, is_real = send_verification_otp(phone)
    return {
        "success": success,
        "message": message,
        "is_real_sms": is_real,
        "phone": phone,
    }


@router.post("/otp/verify", response_model=Token)
@limiter.limit(OTP_RATE_LIMIT)
def verify_and_login_otp(request: Request, data: OtpVerifyRequest, db: Session = Depends(get_db)):
    """
    Verify SMS OTP and issue signed JWT bearer token.
    """
    phone = normalize_phone(data.phone)
    if not verify_otp(data.otp, phone=phone):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP code.",
        )

    # Find customer
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    cust_id = customer.customer_id if customer else None

    # Find or create user record
    username = f"user_{phone}"
    user = db.query(User).filter((User.username == username) | (User.phone == phone)).first()
    if not user:
        user = User(
            username=username,
            phone=phone,
            email=customer.email if customer else f"{username}@telecom.local",
            hashed_password=hash_password("OTP_AUTH_VERIFIED"),
            customer_id=cust_id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({
        "sub": user.username,
        "customer_id": user.customer_id,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "customer_id": user.customer_id,
        "username": user.username,
    }
