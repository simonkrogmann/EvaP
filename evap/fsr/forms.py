from django import forms
from django.forms.models import BaseInlineFormSet, BaseModelFormSet
from django.utils.translation import ugettext_lazy as _

from evaluation.models import *
from student.forms import GRADE_CHOICES, coerce_grade
from fsr.fields import *

class ImportForm(forms.Form):
    vote_start_date = forms.DateField(label = _(u"first date to vote"))
    vote_end_date = forms.DateField(label = _(u"last date to vote"))
    
    excel_file = forms.FileField(label = _(u"excel file"))
    
class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester

class CourseForm(forms.ModelForm):   
    participants = UserModelMultipleChoiceField(queryset=User.objects.all())
    primary_lecturers = UserModelMultipleChoiceField(queryset=User.objects.all())
    secondary_lecturers = UserModelMultipleChoiceField(queryset=User.objects.all())
    
    class Meta:
        model = Course
        exclude = ("voters", "semester")
    
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)
        self.fields['general_questions'].queryset = QuestionGroup.objects.filter(obsolete=False)
        self.fields['primary_lecturer_questions'].queryset = QuestionGroup.objects.filter(obsolete=False)
        self.fields['secondary_lecturer_questions'].queryset = QuestionGroup.objects.filter(obsolete=False)
        self.fields['secondary_lecturers'].required = False

class QuestionGroupForm(forms.ModelForm):
    class Meta:
        model = QuestionGroup
        
ACTION_CHOICES = (
    (u"1", _(u"Approved")),
    (u"2", _(u"Censored")),
    (u"3", _(u"Hide")),
    (u"4", _(u"Needs further review")),
)

class CensorTextAnswerForm(forms.ModelForm):
    class Meta:
        model = TextAnswer
        fields = ('censored_answer',)
    
    def __init__(self, *args, **kwargs):
        super(CensorTextAnswerForm, self).__init__(*args, **kwargs)
        self.fields['action'] = forms.TypedChoiceField(widget=forms.RadioSelect(), choices=ACTION_CHOICES, coerce=int)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        action = cleaned_data.get("action")
        censored_answer = cleaned_data.get("censored_answer")
        
        print action == 2
        print bool(censored_answer)
        
        if action == 2 and not censored_answer:
            raise forms.ValidationError(_(u'Censored answer missing.'))
        
        return cleaned_data

class QuestionFormSet(BaseInlineFormSet):
    def is_valid(self):
        return super(QuestionFormSet, self).is_valid() and not any([bool(e) for e in self.errors])  
    
    def clean(self):          
        # get forms that actually have valid data
        count = 0
        for form in self.forms:
            try:
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    count += 1
            except AttributeError:
                # annoyingly, if a subform is invalid Django explicity raises
                # an AttributeError for cleaned_data
                pass
        
        if count < 1:
            raise forms.ValidationError(_(u'You must have at least one of these.'))

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
    
    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        self.fields['text_de'].widget=forms.TextInput()
        self.fields['text_en'].widget=forms.TextInput()

class QuestionGroupPreviewForm(forms.Form):
    """Dynamic form class that adds one field per question. Pass an iterable
    of questionnaires as `questionnaires` argument to the initializer.
    
    See http://jacobian.org/writing/dynamic-form-generation/"""
    
    def __init__(self, *args, **kwargs):
        questiongroup = kwargs.pop('questiongroup')
        super(QuestionGroupPreviewForm, self).__init__(*args, **kwargs)
        
        # iterate over all questions in the questiongroup
        for question in questiongroup.question_set.all():
            # generic arguments for all kinds of fields
            field_args = dict(label=question.text)
            
            if question.is_text_question():
                field = forms.CharField(widget=forms.Textarea(), required=False, **field_args)
            elif question.is_grade_question():
                field = forms.TypedChoiceField(widget=forms.RadioSelect(), choices=GRADE_CHOICES, coerce=coerce_grade, **field_args)
            
            # create a field for the question, using the ids of both the
            # questionnaire and the question
            self.fields['question_%d' % (question.id)] = field

class QuestionGroupsAssignForm(forms.Form):
    
    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester')
        extras = kwargs.pop('extras', ())
        super(QuestionGroupsAssignForm, self).__init__(*args, **kwargs)
        
        # course kinds
        for kind in semester.course_set.values_list('kind', flat=True).order_by().distinct():
            self.fields[kind] = forms.ModelMultipleChoiceField(required=False, queryset=QuestionGroup.objects.filter(obsolete=False))
        
        # extra kinds
        for extra in extras:
            self.fields[extra] = forms.ModelMultipleChoiceField(required=False, queryset=QuestionGroup.objects.filter(obsolete=False))

class PublishCourseFormSet(BaseModelFormSet):
    class PseudoQuerySet(list):
        db = None
    
    def get_queryset(self):
        if not hasattr(self, '_queryset'):
            self._queryset = PublishCourseFormSet.PseudoQuerySet()
            self._queryset.extend([e for e in self.queryset.all() if e.fully_checked()])
            self._queryset.db = self.queryset.db
        return self._queryset
    
class UserForm(forms.ModelForm):
    username = forms.CharField()
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.CharField(required=False)
    
    proxies = UserModelMultipleChoiceField(queryset=User.objects.all())
    
    class Meta:
        model = UserProfile
        exclude = ('user',)
        fields = ['username', 'title', 'first_name', 'last_name', 'email', 'picture', 'proxies']
    
    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        
        # fix generated form
        self.fields['proxies'].required=False
        
        # load user fields
        self.fields['username'].initial = self.instance.user.username
        self.fields['first_name'].initial = self.instance.user.first_name
        self.fields['last_name'].initial = self.instance.user.last_name
        self.fields['email'].initial = self.instance.user.email

    def save(self, *args, **kw):
        # first save the user, so that the profile gets created for sure
        self.instance.user.username     = self.cleaned_data.get('username')
        self.instance.user.first_name   = self.cleaned_data.get('first_name')
        self.instance.user.last_name    = self.cleaned_data.get('last_name')
        self.instance.user.email        = self.cleaned_data.get('email')
        self.instance.user.save()
        self.instance = self.instance.user.get_profile()
        
        super(UserForm, self).save(*args, **kw)
