from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Post, Comment, UserProfile, Tag


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=[
        ('subscriber', 'Subscriber — Browse and comment on posts'),
        ('contributor', 'Contributor — contribute posts'),
    ])

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'role']

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            role = self.cleaned_data.get('role', 'subscriber')
            UserProfile.objects.get_or_create(user=user, defaults={'role': role})
        return user


class PostForm(forms.ModelForm):
    tags_input = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. python, django, web'}),
        label='Tags (comma separated)'
    )

    class Meta:
        model = Post
        fields = ['title', 'content', 'featured_image', 'category', 'status']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 14, 'id': 'post-content'}),
            'title': forms.TextInput(attrs={'placeholder': 'Enter a compelling title...'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Authors cannot set status — always saves as draft
        if self.user:
            try:
                profile = self.user.profile
                if not profile.is_editor():
                    self.fields.pop('status')
            except UserProfile.DoesNotExist:
                self.fields.pop('status')

        if self.instance.pk:
            self.fields['tags_input'].initial = ', '.join(
                tag.name for tag in self.instance.tags.all()
            )

    def save(self, commit=True):
        post = super().save(commit=False)
        # Authors always draft
        if self.user:
            try:
                if not self.user.profile.is_editor() and 'status' not in self.fields:
                    post.status = 'draft'
            except UserProfile.DoesNotExist:
                post.status = 'draft'
        if commit:
            post.save()
            tags_input = self.cleaned_data.get('tags_input', '')
            post.tags.clear()
            for tag_name in [t.strip() for t in tags_input.split(',') if t.strip()]:
                tag, _ = Tag.objects.get_or_create(name__iexact=tag_name, defaults={'name': tag_name})
                post.tags.add(tag)
        return post


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Share your thoughts...'}),
        }
        labels = {'content': ''}


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['bio', 'avatar']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tell readers about yourself...'}),
        }