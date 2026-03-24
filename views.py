from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q
from .models import Post, Comment, UserProfile, Category, Tag
from .forms import RegisterForm, PostForm, CommentForm, UserProfileForm


# ─── Helpers ────────────────────────────────────────────────────────────────

def get_role(user):
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return 'reader'


def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'reader'})
    return profile


# ─── Auth Views ─────────────────────────────────────────────────────────────

def register(request):
    if request.user.is_authenticated:
        return redirect('post_list')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('post_list')
    else:
        form = RegisterForm()
    return render(request, 'blog/register.html', {'form': form})


def user_login(request):
    if request.user.is_authenticated:
        return redirect('post_list')
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            ensure_profile(user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect(request.GET.get('next', 'post_list'))
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    return render(request, 'blog/login.html', {'form': form})


def user_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('post_list')


# ─── Post List ──────────────────────────────────────────────────────────────

def post_list(request):
    posts = Post.objects.filter(status='published').select_related('author', 'category')
    categories = Category.objects.all()
    tags = Tag.objects.all()

    # Filters
    category_slug = request.GET.get('category')
    tag_slug = request.GET.get('tag')
    search = request.GET.get('search', '')

    if category_slug:
        posts = posts.filter(category__slug=category_slug)
    if tag_slug:
        posts = posts.filter(tags__slug=tag_slug)
    if search:
        posts = posts.filter(Q(title__icontains=search) | Q(content__icontains=search))

    context = {
        'posts': posts,
        'categories': categories,
        'tags': tags,
        'search': search,
        'selected_category': category_slug,
        'selected_tag': tag_slug,
    }
    return render(request, 'blog/post_list.html', context)


# ─── Post Detail ────────────────────────────────────────────────────────────

def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug)

    # Non-editors can only see published posts
    if post.status == 'draft':
        if not request.user.is_authenticated:
            return redirect('login')
        profile = ensure_profile(request.user)
        if post.author != request.user and not profile.is_editor():
            messages.error(request, 'This post is not published yet.')
            return redirect('post_list')

    comments = post.comments.select_related('author')
    comment_form = CommentForm()

    if request.method == 'POST' and request.user.is_authenticated:
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()
            messages.success(request, 'Comment added!')
            return redirect('post_detail', slug=slug)

    user_liked = request.user.is_authenticated and post.likes.filter(id=request.user.id).exists()

    context = {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'user_liked': user_liked,
        'like_count': post.like_count(),
    }
    return render(request, 'blog/post_detail.html', context)


# ─── Like / Unlike ──────────────────────────────────────────────────────────

@login_required
def toggle_like(request, slug):
    post = get_object_or_404(Post, slug=slug, status='published')

    user = request.user

    if post.likes.filter(id=user.id).exists():
        post.likes.remove(user)
        liked = False
    else:
        post.likes.add(user)
        liked = True

    return JsonResponse({
        "liked": liked,
        "count": post.like_count()
    })


# ─── Create Post ────────────────────────────────────────────────────────────

@login_required
def create_post(request):
    profile = ensure_profile(request.user)
    if not profile.is_contributor():
        messages.error(request, 'You need contributor role or higher to create posts.')
        return redirect('post_list')

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            form.save_m2m()
            form.save()  # saves tags
            messages.success(request, 'Post created successfully!')
            return redirect('post_detail', slug=post.slug)
    else:
        form = PostForm(user=request.user)

    return render(request, 'blog/post_form.html', {'form': form, 'action': 'Create'})


# ─── Edit Post ──────────────────────────────────────────────────────────────

@login_required
def edit_post(request, slug):
    post = get_object_or_404(Post, slug=slug)
    profile = ensure_profile(request.user)

    # Authors can only edit their own; editors can edit any
    if post.author != request.user and not profile.is_editor():
        return HttpResponseForbidden("You don't have permission to edit this post.")

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Post updated successfully!')
            return redirect('post_detail', slug=post.slug)
    else:
        form = PostForm(instance=post, user=request.user)

    return render(request, 'blog/post_form.html', {'form': form, 'post': post, 'action': 'Edit'})


# ─── Delete Post ────────────────────────────────────────────────────────────

@login_required
def delete_post(request, slug):
    post = get_object_or_404(Post, slug=slug)
    profile = ensure_profile(request.user)

    if post.author != request.user and not profile.is_editor():
        return HttpResponseForbidden("You don't have permission to delete this post.")

    if request.method == 'POST':
        post.delete()
        messages.success(request, 'Post deleted.')
        return redirect('post_list')

    return render(request, 'blog/post_confirm_delete.html', {'post': post})


# ─── Draft Posts ────────────────────────────────────────────────────────────

@login_required
def draft_posts(request):
    profile = ensure_profile(request.user)
    if profile.is_editor():
        # Editors see ALL drafts
        drafts = Post.objects.filter(status='draft').select_related('author')
    else:
        # Authors see only their own drafts
        drafts = Post.objects.filter(status='draft', author=request.user)
    return render(request, 'blog/draft_posts.html', {'drafts': drafts})


# ─── Publish Post (Editor/Admin only) ───────────────────────────────────────

@login_required
def publish_post(request, slug):

    post = get_object_or_404(Post, slug=slug)
    profile = ensure_profile(request.user)

    # Contributors cannot publish posts
    if profile.role == "contributor":
        return HttpResponseForbidden("Contributors cannot publish posts.")

    # Authors can publish only their own posts
    if profile.role == "author" and post.author != request.user:
        return HttpResponseForbidden("Authors can only publish their own posts.")

    # Editors and Admins can publish any post
    post.status = "published"
    post.save()

    messages.success(request, f'"{post.title}" is now published!')
    return redirect("post_detail", slug=post.slug)


# ─── User Dashboard ─────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    profile = ensure_profile(request.user)

    if profile.is_editor():
        my_posts = Post.objects.filter(author=request.user)
        pending_posts = Post.objects.filter(status='draft').exclude(author=request.user)
    else:
        my_posts = Post.objects.filter(author=request.user)
        pending_posts = None

    context = {
        'profile': profile,
        'my_posts': my_posts,
        'pending_posts': pending_posts,
    }
    return render(request, 'blog/dashboard.html', context)


# ─── Profile ────────────────────────────────────────────────────────────────

@login_required
def edit_profile(request):
    profile = ensure_profile(request.user)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated!')
            return redirect('dashboard')
    else:
        form = UserProfileForm(instance=profile)
    return render(request, 'blog/edit_profile.html', {'form': form})


# ─── Admin: Manage Users ────────────────────────────────────────────────────

@login_required
def manage_users(request):
    profile = ensure_profile(request.user)
    if not profile.is_admin():
        return HttpResponseForbidden("Admin access only.")

    profiles = UserProfile.objects.select_related('user').all()

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        new_role = request.POST.get('role')
        if user_id and new_role in dict(UserProfile.ROLE_CHOICES):
            target = get_object_or_404(UserProfile, user_id=user_id)
            target.role = new_role
            target.save()
            messages.success(request, f"Role updated for {target.user.username}.")
        return redirect('manage_users')

    return render(request, 'blog/manage_users.html', {'profiles': profiles})